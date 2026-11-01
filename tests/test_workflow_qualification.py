import importlib
import pytest


def test_deadline_is_not_swallowed_by_worker_exception_handlers(monkeypatch):
    import signal
    from scripts.run_workflow_qualification import install_deadline
    seen = []
    monkeypatch.setattr(signal, 'signal', lambda sig, handler: seen.append(handler))
    monkeypatch.setattr(signal, 'alarm', lambda seconds: seen.append(seconds))
    install_deadline()
    assert seen[1] == 300
    with pytest.raises(SystemExit, match='deadline'):
        seen[0](None, None)


def test_qualification_rejects_unknown_worker_before_import():
    from scripts.run_workflow_qualification import validate
    with pytest.raises(ValueError, match='Unsupported'):
        validate('scrape_jobs', 'technology_delivery', {'JOB_DATA_API_URL': 'https://api.example.test', 'JOB_DATA_API_TOKEN': 'test'})


def test_qualification_requires_explicit_authority_and_single_canonical_lane():
    from scripts.run_workflow_qualification import validate
    for env, lane in [({}, 'technology_delivery'), ({'JOB_DATA_API_URL': 'https://api.example.test'}, 'technology_delivery'), ({'JOB_DATA_API_URL': 'https://api.example.test', 'JOB_DATA_API_TOKEN': 'test'}, '')]:
        with pytest.raises(ValueError):
            validate('analyze_jobs', lane, env)


def test_provider_budget_counts_failed_attempts_and_caps_payload():
    from scripts.run_workflow_qualification import bounded_completion
    seen = []
    def provider(**kwargs):
        seen.append(kwargs)
        raise RuntimeError('provider unavailable')
    call = bounded_completion(provider, requests=2)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='unavailable'):
            call(messages=[{'role': 'user', 'content': 'bounded'}], max_tokens=99999, num_retries=9)
    with pytest.raises(RuntimeError, match='qualification request budget'):
        call(messages=[])
    assert len(seen) == 2
    assert all(x['max_tokens'] == 4096 and x['num_retries'] == 0 for x in seen)
    with pytest.raises(ValueError, match='prompt'):
        bounded_completion(provider)(messages=[{'content': 'x' * 50001}])


def test_worker_bounds_and_no_backlog_or_filter_prepass(monkeypatch):
    from scripts.run_workflow_qualification import execute
    import config
    seen = []
    class Worker:
        def main(self, lane, **kwargs):
            seen.append((lane, kwargs, config.JOBS_TO_SCORE_PER_RUN, config.JOB_SCORE_BATCH_SIZE))
            return {'status': 'completed'}
        def scoring_result_exit_code(self, result):
            return 0
    assert execute('score_jobs', 'technology_delivery', importer=lambda name: Worker()) == {'status': 'completed'}
    assert seen == [('technology_delivery', {'run_filter_prepass': False}, 1, 1)]


def test_workflow_qualification_wiring_preserves_default_worker():
    from pathlib import Path
    import yaml
    from scripts.run_workflow_qualification import WORKERS
    root = Path(__file__).resolve().parents[1]
    for worker in WORKERS:
        workflow = yaml.safe_load((root / '.github/workflows' / (worker + '.yml')).read_text())
        assert workflow[True]['workflow_dispatch']['inputs']['qualification']['default'] is False
        steps = [s for j in workflow['jobs'].values() for s in j['steps'] if 'run_workflow_qualification' in s.get('run', '')]
        assert len(steps) == 1
        assert steps[0]['env']['WORKFLOW_QUALIFICATION'] == '${{ inputs.qualification }}'
        assert '--workflow ' + worker in steps[0]['run']
