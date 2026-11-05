import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import pytest


@pytest.fixture
def created_recovery(monkeypatch, tmp_path):
    """Real entrypoint with only database/source boundaries doubled."""
    import copy
    import json
    import os
    from types import SimpleNamespace
    import history_recovery as recovery
    import linkedin_discovery as discovery

    targets = recovery_environment(monkeypatch, tmp_path)
    for target in targets:
        target['definition'] = {'query': 'audited-' + target['scope_key']}
    Path(os.environ['LINKEDIN_HISTORY_TARGETS']).write_text(json.dumps(targets))
    scopes = [{
        'scope_key': t['scope_key'], 'scope_definition': t['definition'],
        'source_window_earliest_at': '2026-08-06T00:00:00+00:00',
        'source_window_latest_at': '2026-11-04T00:00:00+00:00',
        'query_scope': '{}', 'ingestion_run_id': t['scope_key'],
    } for t in targets]
    created = {'cycle_id': 55, 'discovery_sequence': 57, 'search_status': 'running',
               'scopes': [{k: v for k, v in s.items() if k != 'scope_definition'} for s in scopes]}
    persisted = {**copy.deepcopy(created), 'scopes': copy.deepcopy(scopes[::-1])}
    calls, guarded = [], []
    def selector(**kwargs):
        calls.append(kwargs)
        return None if len(calls) == 1 else persisted
    db = discovery.supabase_utils
    monkeypatch.setattr(db, 'get_resumable_linkedin_discovery_cycle', selector)
    monkeypatch.setattr(db, 'create_linkedin_discovery_cycle', lambda **kw: created)
    monkeypatch.setattr(recovery, 'require_drained_queue', lambda db: None)
    keys = iter(t['scope_key'] for t in targets)
    monkeypatch.setattr(discovery, 'scope_definition', lambda *a: {})
    monkeypatch.setattr(discovery, 'scope_key', lambda *a: next(keys))
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: copy.deepcopy(scopes))
    monkeypatch.setattr(discovery, 'configuration_hash', lambda *a: 'offline')
    original_guard = recovery.require_manifest
    def guard(cycle):
        guarded.append(cycle)
        original_guard(cycle)
    monkeypatch.setattr(recovery, 'require_manifest', guard)
    class GuardPassed(Exception):
        pass
    def gate(*a, **kw):
        raise GuardPassed('manifest accepted before source gate')
    monkeypatch.setattr(discovery, 'DurableLinkedInRequestGate', gate)
    def forbidden_source(*args, **kwargs) -> NoReturn:
        raise AssertionError('source GET before guard')
    monkeypatch.setattr(discovery, '_request_page', forbidden_source)
    configuration = SimpleNamespace(revision=10, settings=SimpleNamespace(
        max_pages_per_query=1, max_jobs_per_query=50, options={'outage_recovery_cap_hours': 2160}))
    def run():
        return discovery.run_discovery(configuration, [SimpleNamespace() for _ in targets],
            parse_cards=forbidden_source, detail_fetch=forbidden_source, save_details=forbidden_source, partial=False)
    return SimpleNamespace(run=run, created=created, persisted=persisted,
                           calls=calls, guarded=guarded, GuardPassed=GuardPassed)


def test_created_recovery_hydrates_from_independent_exact_selector(created_recovery):
    case = created_recovery
    with pytest.raises(case.GuardPassed):
        case.run()
    assert case.calls == [{'partial': False, 'scope_keys': None}] * 2
    assert case.guarded == [case.persisted]
    assert case.guarded[0] is case.persisted
    assert all('scope_definition' not in s for s in case.created['scopes'])


@pytest.mark.parametrize('side', ['created', 'persisted'])
@pytest.mark.parametrize('field', ['cycle_id', 'discovery_sequence'])
@pytest.mark.parametrize('value', [None, True, '55', 54, 99])
def test_created_recovery_rejects_unbound_identity(created_recovery, side, field, value):
    case = created_recovery
    getattr(case, side)[field] = value
    with pytest.raises(RuntimeError, match='recovery readback identity'):
        case.run()
    assert not case.guarded


@pytest.mark.parametrize('failure', [
    'missing', 'extra', 'duplicate', 'wrong_key', 'earliest', 'latest',
    'expired', 'truncated', 'run_id', 'missing_definition', 'null_definition',
])
def test_created_recovery_rejects_incomplete_or_changed_readback(created_recovery, failure):
    case = created_recovery
    scopes = case.persisted['scopes']
    if failure == 'missing': scopes.pop()
    if failure == 'extra': scopes.append({**scopes[0], 'scope_key': 'extra'})
    if failure == 'duplicate': scopes[0] = scopes[1].copy()
    if failure == 'wrong_key': scopes[0]['scope_key'] = 'wrong'
    if failure == 'earliest': scopes[0]['source_window_earliest_at'] = '2026-08-01T00:00:00+00:00'
    if failure == 'latest': scopes[0]['source_window_latest_at'] = '2026-11-05T00:00:00+00:00'
    if failure == 'expired': scopes[0]['expired_window_latest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'truncated': scopes[0]['truncated_window_latest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'run_id': scopes[0]['ingestion_run_id'] = 'another-run'
    if failure == 'missing_definition': scopes[0].pop('scope_definition')
    if failure == 'null_definition': scopes[0]['scope_definition'] = None
    with pytest.raises(RuntimeError, match='recovery readback scope'):
        case.run()
    assert not case.guarded


@pytest.mark.parametrize('failure', ['definition', 'narrow', 'late', 'expired', 'truncated'])
def test_hydrated_recovery_still_requires_original_manifest_guard(created_recovery, failure):
    case = created_recovery
    scope = case.persisted['scopes'][0]
    original = next(s for s in case.created['scopes'] if s['scope_key'] == scope['scope_key'])
    if failure == 'definition': scope['scope_definition'] = {'query': 'wrong'}
    if failure == 'narrow': scope['source_window_earliest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'late': scope['source_window_latest_at'] = '2026-10-01T00:00:00+00:00'
    if failure == 'expired': scope['expired_window_latest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'truncated': scope['truncated_window_latest_at'] = '2026-09-16T00:00:00+00:00'
    original.update({k: v for k, v in scope.items() if k != 'scope_definition'})
    with pytest.raises(RuntimeError, match='persisted recovery'):
        case.run()
    assert case.guarded == [case.persisted]


@pytest.mark.parametrize('result', [None, {}])
def test_created_recovery_rejects_missing_selector_result(created_recovery, monkeypatch, result):
    import linkedin_discovery as discovery
    case = created_recovery
    responses = iter([None, result])
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: next(responses))
    with pytest.raises(RuntimeError, match='recovery readback identity'):
        case.run()
    assert not case.guarded


def test_created_recovery_propagates_selector_failure_before_source(created_recovery, monkeypatch):
    import linkedin_discovery as discovery
    case = created_recovery
    def selector(**kwargs):
        case.calls.append(kwargs)
        if len(case.calls) == 1:
            return None
        raise RuntimeError('readback unavailable')
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', selector)
    with pytest.raises(RuntimeError, match='readback unavailable'):
        case.run()
    assert not case.guarded


@pytest.mark.parametrize('mode', [None, 'resume'])
def test_hydration_does_not_change_ordinary_or_resume_paths(created_recovery, monkeypatch, mode):
    import linkedin_discovery as discovery
    case = created_recovery
    if mode is None:
        monkeypatch.delenv('LINKEDIN_HISTORY_RECOVERY')
    else:
        monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'resume')
        monkeypatch.setenv('LINKEDIN_HISTORY_CYCLE_ID', '55')
        monkeypatch.setenv('LINKEDIN_HISTORY_SEQUENCE', '57')
        case.persisted['pinned_user_agent'] = 'persisted-agent'
        case.calls.append('skip initial empty selector')
        monkeypatch.setattr(discovery, '_resumable_scope_manifest', lambda scope: dict(scope))
        monkeypatch.setattr(discovery.supabase_utils, 'create_linkedin_discovery_cycle',
                            lambda **kw: pytest.fail('resume must not create a cycle'))
    with pytest.raises(case.GuardPassed):
        case.run()
    assert len(case.calls) == (1 if mode is None else 2)
    assert case.guarded == [case.created if mode is None else case.persisted]


def test_only_local_cap_changes_in_full_export():
    spec = importlib.util.spec_from_file_location('history_recovery', Path(__file__).parents[1] / 'history_recovery.py')
    assert spec is not None and spec.loader is not None
    assert Path(spec.origin).exists(), 'missing executable recovery guard/export module'
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = {'revision': 10, 'settings': {'options': {}, 'lookback_days': 2}, 'lanes': [{'keep': True}]}
    result = module.with_recovery_cap(original)
    assert result == {'revision': 10, 'settings': {'options': {'outage_recovery_cap_hours': 2160}, 'lookback_days': 2}, 'lanes': [{'keep': True}]}
    assert original['settings']['options'] == {}


def test_selection_refuses_old_resume_before_manifest_preparation(monkeypatch):
    import history_recovery as recovery
    monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'new')
    with pytest.raises(RuntimeError, match='new recovery requires no resumable cycle'):
        recovery.require_selection({'cycle_id': 54}, {}, partial=False, scope_keys=[])


def recovery_environment(monkeypatch, tmp_path):
    import json
    targets = [{'scope_key': str(i), 'original_gap_intervals': [{'earliest_at': '2026-09-15T21:32:36.890075+00:00', 'latest_at': '2026-10-27T20:53:06.886095+00:00'}]} for i in range(13)]
    path = tmp_path / 'targets.json'
    path.write_text(json.dumps(targets))
    for key, value in {'LINKEDIN_HISTORY_RECOVERY': 'new', 'LINKEDIN_HISTORY_TARGETS': str(path), 'SCRAPE_CONFIG_SOURCE': 'file', 'LINKEDIN_RECOVERY_LOOKBACK_HOURS': '2160'}.items():
        monkeypatch.setenv(key, value)
    return targets


@pytest.mark.parametrize('failure', ['partial', 'scope', 'cap', 'budget', 'source', 'override', 'missing_resume', 'old_resume', 'wrong_resume', 'invalid_mode'])
def test_selection_fails_closed(monkeypatch, tmp_path, failure):
    import history_recovery as recovery
    targets = recovery_environment(monkeypatch, tmp_path)
    options = {'recovery_cap': 2160, 'attempts': 800, 'detail_attempts': 800, 'detail': 300, 'search_runtime': 1620, 'detail_runtime': 300}
    keys = [t['scope_key'] for t in targets]
    partial = failure == 'partial'
    cycle = None
    if failure == 'scope': keys.pop()
    if failure == 'cap': options['recovery_cap'] = 168
    if failure == 'budget': options['attempts'] = 801
    if failure == 'source': monkeypatch.setenv('SCRAPE_CONFIG_SOURCE', 'db')
    if failure == 'override': monkeypatch.delenv('LINKEDIN_RECOVERY_LOOKBACK_HOURS')
    if failure in {'missing_resume', 'old_resume', 'wrong_resume'}:
        monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'resume')
        monkeypatch.setenv('LINKEDIN_HISTORY_CYCLE_ID', '55')
        monkeypatch.setenv('LINKEDIN_HISTORY_SEQUENCE', '55')
        cycle = None if failure == 'missing_resume' else {'cycle_id': 54 if failure == 'old_resume' else 56, 'discovery_sequence': 55}
    if failure == 'invalid_mode': monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'typo')
    with pytest.raises(RuntimeError):
        recovery.require_selection(cycle, options, partial=partial, scope_keys=keys)


@pytest.mark.parametrize('detail', [300, 301])
def test_selection_enforces_detail_task_ceiling(monkeypatch, tmp_path, detail):
    import history_recovery as recovery
    targets = recovery_environment(monkeypatch, tmp_path)
    options = {'recovery_cap': 2160, 'attempts': 800, 'detail_attempts': 800, 'detail': detail, 'search_runtime': 1620, 'detail_runtime': 300}
    if detail == 301:
        with pytest.raises(RuntimeError, match='historical recovery budget exceeds reviewed envelope'):
            recovery.require_selection(None, options, partial=False, scope_keys=[t['scope_key'] for t in targets])
    else:
        recovery.require_selection(None, options, partial=False, scope_keys=[t['scope_key'] for t in targets])


def test_selection_accepts_exact_new_or_resume(monkeypatch, tmp_path):
    import history_recovery as recovery
    targets = recovery_environment(monkeypatch, tmp_path)
    options = {'recovery_cap': 2160, 'attempts': 800, 'detail_attempts': 800, 'detail': 300, 'search_runtime': 1620, 'detail_runtime': 300}
    recovery.require_selection(None, options, partial=False, scope_keys=[t['scope_key'] for t in targets])
    monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'resume')
    monkeypatch.setenv('LINKEDIN_HISTORY_CYCLE_ID', '55')
    monkeypatch.setenv('LINKEDIN_HISTORY_SEQUENCE', '55')
    recovery.require_selection({'cycle_id': 55, 'discovery_sequence': 55}, options, partial=False, scope_keys=[t['scope_key'] for t in targets])


@pytest.mark.parametrize('failure', ['old_cycle', 'missing_scope', 'narrow', 'truncated', 'late', 'definition'])
def test_persisted_manifest_must_cover_original_gaps(monkeypatch, tmp_path, failure):
    import history_recovery as recovery
    targets = recovery_environment(monkeypatch, tmp_path)
    scopes = [{'scope_key': t['scope_key'], 'source_window_earliest_at': '2026-08-06T00:00:00+00:00', 'source_window_latest_at': '2026-11-04T00:00:00+00:00'} for t in targets]
    cycle = {'cycle_id': 55, 'discovery_sequence': 55, 'scopes': scopes}
    if failure == 'old_cycle': cycle['cycle_id'] = 54
    if failure == 'missing_scope': scopes.pop()
    if failure == 'narrow': scopes[0]['source_window_earliest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'truncated': scopes[0]['expired_window_latest_at'] = '2026-09-16T00:00:00+00:00'
    if failure == 'late': scopes[0]['source_window_latest_at'] = '2026-10-01T00:00:00+00:00'
    if failure == 'definition':
        targets[0]['definition'] = {'query': 'expected'}
        import json
        Path(__import__('os').environ['LINKEDIN_HISTORY_TARGETS']).write_text(json.dumps(targets))
        scopes[0]['scope_definition'] = {'query': 'wrong'}
    with pytest.raises(RuntimeError):
        recovery.require_manifest(cycle)


def test_persisted_broad_manifest_is_accepted(monkeypatch, tmp_path):
    import history_recovery as recovery
    targets = recovery_environment(monkeypatch, tmp_path)
    recovery.require_manifest({'cycle_id': 55, 'discovery_sequence': 55, 'scopes': [{'scope_key': t['scope_key'], 'source_window_earliest_at': '2026-08-06T00:00:00+00:00', 'source_window_latest_at': '2026-11-04T00:00:00+00:00'} for t in targets]})



def test_original_entrypoint_rejects_old_resume_before_any_preparation(monkeypatch):
    from types import SimpleNamespace
    import linkedin_discovery as discovery
    monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'new')
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: {'cycle_id': 54})
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: pytest.fail('must not prepare scope/debt or make source requests'))
    with pytest.raises(RuntimeError, match='new recovery requires no resumable cycle'):
        discovery.run_discovery(SimpleNamespace(settings=SimpleNamespace(max_pages_per_query=6, max_jobs_per_query=50, options={})), [], parse_cards=None, detail_fetch=None, save_details=None, partial=False)


@pytest.mark.parametrize('count', [1, None, True])
def test_new_recovery_requires_empty_global_queue(monkeypatch, count):
    import history_recovery as recovery
    from types import SimpleNamespace
    class Query:
        def table(self, *a): return self
        def select(self, *a, **kw): return self
        def in_(self, *a): return self
        def execute(self): return SimpleNamespace(count=count)
    monkeypatch.setenv('LINKEDIN_HISTORY_RECOVERY', 'new')
    with pytest.raises(RuntimeError, match='drain'):
        recovery.require_drained_queue(Query())


def test_persisted_guard_is_wired_before_source_gate():
    import inspect
    import linkedin_discovery as discovery
    source = inspect.getsource(discovery.run_discovery)
    assert 'history_recovery.require_manifest(cycle)' in source
    assert source.index('history_recovery.require_manifest(cycle)') < source.index('gate = DurableLinkedInRequestGate')



def test_executable_export_preserves_full_document(tmp_path):
    import json
    import subprocess
    import sys
    original = {'version': 1, 'revision': 10, 'settings': {'options': {}, 'lookback_days': 2}, 'lanes': [], 'aliases': []}
    source = tmp_path / 'actual.json'
    output = tmp_path / 'recovery.json'
    source.write_text(json.dumps(original))
    result = subprocess.run([sys.executable, 'history_recovery.py', '--from-file', str(source), '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.exists(), 'CLI must actually export complete configuration'
    expected = json.loads(json.dumps(original))
    expected['settings']['options']['outage_recovery_cap_hours'] = 2160
    assert json.loads(output.read_text()) == expected
    assert output.stat().st_mode & 0o777 == 0o600
    assert subprocess.run([sys.executable, 'history_recovery.py', '--from-file', str(source), '--output', str(output)], capture_output=True).returncode != 0


def test_candidate_workflow_is_manual_scraper_only_and_globally_serialized():
    import yaml
    path = Path('.github/workflows/history_recovery_manual.yml')
    assert path.exists(), 'missing executable historical recovery workflow'
    workflow = yaml.safe_load(path.read_text())
    assert workflow['concurrency'] == {'group': 'linkedin-freehire-pipeline', 'cancel-in-progress': False}
    assert set(workflow.get('on', workflow.get(True))) == {'workflow_dispatch'}
    text = path.read_text()
    assert 'python scraper.py' in text
    assert 'python history_recovery.py --output' in text
    assert 'LINKEDIN_HISTORY_RECOVERY' in text
    assert '2160' in text
    assert 'LLM_API_KEY' not in text
    assert len(workflow['jobs']) == 1



@pytest.mark.parametrize('budget, expected_sealed', [(13, False), (286, True)])
def test_original_pagination_never_truncates_or_calls_budget_exhaustion_empty(monkeypatch, tmp_path, budget, expected_sealed):
    from types import SimpleNamespace
    import linkedin_discovery as discovery
    targets = recovery_environment(monkeypatch, tmp_path)
    definitions = [{'scope_key': t['scope_key'], 'scope_definition': {}, 'source_window_earliest_at': '2026-08-06T00:00:00+00:00', 'source_window_latest_at': '2026-11-04T00:00:00+00:00', 'query_scope': '{}', 'archetype': 'test', 'query': 'test', 'query_id': 'q', 'query_type': 'precision', 'language': 'en', 'location_scope': 'canada', 'geography_id': 'CA', 'ingestion_run_id': t['scope_key']} for t in targets]
    # Match requested keys without replacing the actual scheduler/page loop.
    executions = [SimpleNamespace() for _ in targets]
    iterator = iter([t['scope_key'] for t in targets])
    monkeypatch.setattr(discovery, 'scope_definition', lambda *a: {})
    monkeypatch.setattr(discovery, 'scope_key', lambda *a: next(iterator))
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: definitions)
    monkeypatch.setattr(discovery, 'configuration_hash', lambda *a: 'offline')
    db = discovery.supabase_utils
    persisted = None
    def create(**kw):
        import copy
        nonlocal persisted
        persisted = {'cycle_id': 55, 'discovery_sequence': 55, 'search_status': 'running', 'scopes': copy.deepcopy(kw['scopes'])}
        return {**persisted, 'scopes': [{k: v for k, v in s.items() if k != 'scope_definition'} for s in persisted['scopes']]}
    monkeypatch.setattr(db, 'get_resumable_linkedin_discovery_cycle', lambda **kw: persisted)
    monkeypatch.setattr(discovery.history_recovery if hasattr(discovery, 'history_recovery') else __import__('history_recovery'), 'require_drained_queue', lambda db: None)
    monkeypatch.setattr(db, 'create_linkedin_discovery_cycle', create)
    requested = []
    def request(scope, page, **kw):
        kw['physical_attempts'][0] += 1
        requested.append((scope['scope_key'], page))
        return {'kind': 'no_results' if page == 22 else 'cards'}
    monkeypatch.setattr(discovery, '_request_page', request)
    monkeypatch.setattr(db, 'commit_linkedin_discovery_page', lambda payload: {'new_workflow_source_ids': 1})
    finished, sealed = [], []
    monkeypatch.setattr(db, 'finish_linkedin_discovery_scope', lambda *a, **kw: finished.append(a))
    monkeypatch.setattr(db, 'seal_linkedin_discovery_cycle', lambda *a, **kw: sealed.append(a) or {'watermark_advanced': False})
    monkeypatch.setattr(db, 'resolve_eligible_failed_linkedin_discovery_cycles', lambda *a: [])
    monkeypatch.setattr(db, 'fail_linkedin_discovery_cycle', lambda *a: pytest.fail(str(a)))
    monkeypatch.setattr(discovery, '_drain_tasks', lambda *a, **kw: [])
    configuration = SimpleNamespace(revision=10, settings=SimpleNamespace(max_pages_per_query=1, max_jobs_per_query=50, options={'outage_recovery_cap_hours': 2160, 'max_source_http_attempts_per_run': budget}))
    discovery.run_discovery(configuration, executions, parse_cards=lambda *a: [], detail_fetch=lambda *a: None, save_details=lambda *a: '', partial=False)
    assert bool(sealed) == expected_sealed
    assert len(finished) == (13 if expected_sealed else 0)
    assert len(requested) == budget
    assert max(page for _, page in requested) == (22 if expected_sealed else 1)
