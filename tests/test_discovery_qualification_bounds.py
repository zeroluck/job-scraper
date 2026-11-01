from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
import linkedin_discovery as discovery


def test_search_card_bound_rejects_full_page_without_truncating_evidence(monkeypatch):
    events = []
    scope = {'source_window_earliest_at': datetime.now(timezone.utc).isoformat(),
             'scope_key': 'one', 'query': 'x', 'location': 'x', 'job_type': '', 'work_types': ''}
    grant = SimpleNamespace(started_at=datetime.now(timezone.utc))
    gate = SimpleNamespace(acquire=lambda *a, **kw: grant, finish=lambda *a: events.append(a))
    response = SimpleNamespace(status_code=200, content=b'<li>x</li>', text='<li>x</li>',
        url='https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search', headers={})
    monkeypatch.setattr(discovery.requests, 'get', lambda *a, **kw: response)
    with pytest.raises(discovery.DiscoveryError, match='card envelope'):
        discovery._request_page(scope, 1, user_agent='ua', gate=gate,
            parse_cards=lambda e: [{'job_id': '1'}, {'job_id': '2'}],
            physical_attempts=[0], physical_limit=1, max_cards=1)
    assert events[-1][1] == 'parser_error'


def test_detail_claim_cannot_overrun_task_budget(monkeypatch):
    monkeypatch.setattr(discovery.supabase_utils, 'claim_linkedin_discovery_tasks', lambda *a, **kw: [{'id': 1}, {'id': 2}])
    with pytest.raises(discovery.DiscoveryError, match='claim envelope'):
        discovery._drain_tasks(1, 1, user_agent='ua',
            detail_fetch=lambda *a, **kw: pytest.fail('fetched excess claim'),
            save_details=lambda *a: pytest.fail('wrote excess claim'))


def test_bounded_discovery_rejects_multiple_scopes_before_database_access(monkeypatch):
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: pytest.fail('touched database'))
    with pytest.raises(discovery.DiscoveryError, match='one execution'):
        discovery.run_discovery(None, [object(), object()], parse_cards=lambda e: [],
            detail_fetch=lambda *a: None, save_details=lambda *a: '', partial=True,
            qualification=True)


@pytest.mark.parametrize('resumable', [None, {'scopes': [{}], 'pinned_user_agent': 'ua'}])
def test_qualification_rejects_shared_resume_or_multi_manifest_before_creation(monkeypatch, resumable):
    cfg = SimpleNamespace(settings=SimpleNamespace(options={}, max_pages_per_query=1, max_jobs_per_query=10))
    monkeypatch.setattr(discovery, 'scope_definition', lambda *a: {})
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: resumable)
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: [{}, {}])
    monkeypatch.setattr(discovery.supabase_utils, 'create_linkedin_discovery_cycle', lambda **kw: pytest.fail('created unsafe cycle'))
    with pytest.raises(discovery.DiscoveryError, match='qualification envelope'):
        discovery.run_discovery(cfg, [object()], parse_cards=lambda e: [],
            detail_fetch=lambda *a: None, save_details=lambda *a: '', partial=True, qualification=True)


def test_bounded_discovery_passes_card_limit_to_real_page_boundary(monkeypatch):
    cfg = SimpleNamespace(settings=SimpleNamespace(options={}, max_pages_per_query=1, max_jobs_per_query=10), revision=1)
    monkeypatch.setattr(discovery, 'scope_definition', lambda *a: {})
    monkeypatch.setattr(discovery, 'configuration_hash', lambda *a: 'hash')
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: None)
    scope = {'scope_key': 'one', 'query_scope': '{}', 'ingestion_run_id': 'run-1'}
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: [dict(scope)])
    monkeypatch.setattr(discovery.supabase_utils, 'create_linkedin_discovery_cycle', lambda **kw: {'cycle_id': 1, 'discovery_sequence': 1, 'scopes': [scope]})
    monkeypatch.setattr(discovery.supabase_utils, 'fail_linkedin_discovery_cycle', lambda *a: None)
    class StopAtHTTP(Exception): pass
    def page(*a, **kw):
        assert kw['physical_limit'] == 1
        assert kw['max_cards'] == 1
        raise StopAtHTTP()
    monkeypatch.setattr(discovery, '_request_page', page)
    with pytest.raises(StopAtHTTP):
        discovery.run_discovery(cfg, [object()], parse_cards=lambda e: [],
            detail_fetch=lambda *a: None, save_details=lambda *a: '', partial=True, qualification=True)


def test_qualification_does_not_create_recovery_chain(monkeypatch):
    cfg = SimpleNamespace(settings=SimpleNamespace(options={}, max_pages_per_query=1, max_jobs_per_query=10), revision=1)
    monkeypatch.setattr(discovery, 'scope_definition', lambda *a: {})
    monkeypatch.setattr(discovery, 'configuration_hash', lambda *a: 'hash')
    monkeypatch.setattr(discovery.supabase_utils, 'get_resumable_linkedin_discovery_cycle', lambda **kw: None)
    monkeypatch.setattr(discovery, '_scope_manifest', lambda *a: [{'query_scope': '{}'}])
    calls = []
    def create(**kw):
        calls.append(kw)
        return {'cycle_id': 1, 'search_status': 'failed'}
    monkeypatch.setattr(discovery.supabase_utils, 'create_linkedin_discovery_cycle', create)
    with pytest.raises(discovery.DiscoveryError):
        discovery.run_discovery(cfg, [object()], parse_cards=lambda e: [],
            detail_fetch=lambda *a: None, save_details=lambda *a: '', partial=True, qualification=True)
    assert len(calls) == 1
