import pytest


@pytest.mark.parametrize('worker,module,method,expected', [
    ('analyze_jobs', 'analyze_jobs', 'run', {'archetype': 'technology_delivery', 'backfill_all': False, 'replacement_backfill': False}),
    ('freehire_compat', 'backfill_freehire_compat', 'run', {'apply': True, 'limit': 1, 'drain_backlog': False, 'replacement_backfill': False}),
    ('backfill_linkedin_metadata', 'backfill_linkedin_metadata', 'run', {'limit': 1, 'apply': True}),
    ('backfill_same_id_relists', 'backfill_same_id_relists', 'run', {'limit': 1, 'apply': True}),
    ('parse_resume', 'resume_parser', 'main', {'target': 'technology_delivery'}),
])
def test_each_worker_gets_exact_safe_arguments(worker, module, method, expected):
    from scripts.run_workflow_qualification import execute
    import config
    from types import SimpleNamespace
    before = config.JOB_INSIGHTS_MAX_JOBS
    calls = []
    def invoke(**kwargs):
        calls.append(kwargs)
        return {'invoked': True}
    def importer(name):
        assert name == module
        return SimpleNamespace(**{method: invoke})
    execute(worker, 'technology_delivery', importer=importer)
    assert calls == [expected]
    assert config.JOB_INSIGHTS_MAX_JOBS == before


def test_customization_runs_one_lane_and_restores_bounds():
    from scripts.run_workflow_qualification import execute
    from types import SimpleNamespace
    import config
    calls = []
    async def cycle(**kwargs):
        calls.append((kwargs, config.JOBS_TO_CUSTOMIZE_PER_RUN))
    execute('hourly_resume_customization', 'technology_delivery', importer=lambda _: SimpleNamespace(run_job_processing_cycle=cycle))
    assert calls == [({'archetype': 'technology_delivery'}, 1)]
