"""Opt-in bounded REAL worker execution, not a dry run or an SDK health check.

The caller must independently verify persistent outcomes. Never use this module
as authority to enable a disabled workflow. Scraping and job-manager bulk expiry
are deliberately unsupported until their write envelopes can be bounded.
"""
import argparse
import asyncio
import importlib
import json
import os

WORKERS = (
    'analyze_jobs', 'score_jobs', 'parse_resume', 'hourly_resume_customization',
    'freehire_compat', 'backfill_linkedin_metadata', 'backfill_same_id_relists',
)


def validate(workflow, archetype, env):
    if workflow not in WORKERS:
        raise ValueError('Unsupported qualification worker')
    if not env.get('JOB_DATA_API_URL') or not env.get('JOB_DATA_API_TOKEN'):
        raise ValueError('Explicit target data API authority is required')
    from lane_catalog import LANE_CATALOG
    if archetype not in LANE_CATALOG:
        raise ValueError('One explicit canonical lane is required')


def bounded_completion(provider, requests=2):
    """Count provider invocations INCLUDING errors, across every LLM client."""
    count = 0

    def call(**kwargs):
        nonlocal count
        if len(json.dumps(kwargs.get('messages', []))) > 50000:
            raise ValueError('qualification prompt character budget exceeded')
        if count >= requests:
            raise RuntimeError('qualification request budget exhausted')
        count += 1
        kwargs['max_tokens'] = min(kwargs.get('max_tokens') or 4096, 4096)
        kwargs['num_retries'] = 0
        kwargs['timeout'] = min(kwargs.get('timeout') or 30, 30)
        return provider(**kwargs)

    return call


def execute(workflow, archetype, importer=importlib.import_module):
    """Invoke the intended worker with a small envelope; no fake success rows."""
    import config
    overrides = {
        'JOBS_TO_SCORE_PER_RUN': 1, 'JOB_SCORE_BATCH_SIZE': 1,
        'JOB_INSIGHTS_MAX_JOBS': 1, 'JOB_INSIGHTS_BATCH_SIZE': 1,
        'JOB_INSIGHTS_MAX_RETRIES': 1, 'JOBS_TO_CUSTOMIZE_PER_RUN': 1,
        'FREEHIRE_CLASSIFY_REQUEST_BUDGET': 2, 'FREEHIRE_MAX_BATCH_JOBS': 1,
        'FREEHIRE_CLASSIFY_MAX_RETRIES': 1,
    }
    original = {name: getattr(config, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(config, name, value)
        if workflow == 'score_jobs':
            worker = importer('score_jobs')
            result = worker.main(archetype, run_filter_prepass=False)
            if worker.scoring_result_exit_code(result):
                raise RuntimeError('qualification scoring failed')
            return result
        if workflow == 'analyze_jobs':
            return importer(workflow).run(archetype=archetype, backfill_all=False, replacement_backfill=False)
        if workflow == 'parse_resume':
            importer('resume_parser').main(target=archetype)
            return {'parsed_profiles': 1}
        if workflow == 'hourly_resume_customization':
            asyncio.run(importer('custom_resume_generator').run_job_processing_cycle(archetype=archetype))
            return {'invoked': True, 'readback_required': True}
        if workflow == 'freehire_compat':
            return importer('backfill_freehire_compat').run(apply=True, limit=1, drain_backlog=False, replacement_backfill=False)
        return importer(workflow).run(limit=1, apply=True)
    finally:
        for name, value in original.items():
            setattr(config, name, value)


def install_deadline():
    """Fail the Linux/macOS subprocess even if a worker catches Exception."""
    import signal

    def expired(signum, frame):
        raise SystemExit('qualification deadline exceeded; inspect claims before retry')

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(300)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow', required=True, choices=WORKERS)
    parser.add_argument('--archetype', default=os.getenv('QUALIFICATION_ARCHETYPE', ''))
    args = parser.parse_args(argv)
    validate(args.workflow, args.archetype, os.environ)
    install_deadline()
    # Only this fresh qualification process is affected. The actual provider
    # remains real; retries and model fallbacks share a single hard call budget.
    import litellm
    litellm.completion = bounded_completion(litellm.completion)
    result = execute(args.workflow, args.archetype)
    print(json.dumps({'workflow': args.workflow, 'execution_returned': True,
                      'readback_required': True, 'result': result}, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
