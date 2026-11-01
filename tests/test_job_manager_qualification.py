import asyncio
from types import SimpleNamespace

import httpx
import pytest
import job_manager


@pytest.mark.parametrize('text,inactive', [
    ('Active job description', False),
    ('THIS JOB IS NO LONGER AVAILABLE', True),
    ('No longer accepting applications', True),
])
def test_successful_activity_content_is_classified_and_grant_finished(monkeypatch, text, inactive):
    events = []
    monkeypatch.setattr(job_manager.config, 'ACTIVE_CHECK_MAX_RETRIES', 0)
    monkeypatch.setattr(job_manager, '_linkedin_request_gate', SimpleNamespace(
        acquire=lambda *a: 'grant', finish=lambda *a: events.append(a)))
    class Client:
        async def get(self, *a, **kw):
            return httpx.Response(200, text=text, request=httpx.Request('GET', 'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1'))
    assert asyncio.run(job_manager._check_single_linkedin_job_active('1', Client())) is inactive
    assert events == [('grant', 'terminal_unavailable' if inactive else 'complete', 200)]

@pytest.mark.parametrize('result', [None, RuntimeError('offline check failure'), False, True])
def test_unscoped_activity_preserves_ordinary_failure_and_update_behavior(monkeypatch, result):
    db = Database([{'job_id': '1', 'latest_job_id': 'live-99'}])
    monkeypatch.setattr(job_manager, 'supabase', db)
    async def check(live_id, client, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(job_manager, '_check_single_linkedin_job_active', check)
    asyncio.run(job_manager.check_linkedin_job_activity())
    assert len(db.calls) == (2 if type(result) is bool else 1)
    if type(result) is bool:
        assert ('eq', 'provider', 'linkedin') not in db.calls[1].ops
        assert ('eq', 'is_active', True) not in db.calls[1].ops


@pytest.mark.parametrize('status', [500, 502, 400])
@pytest.mark.parametrize('scoped', [True, False])
def test_http_failure_is_indeterminate_only_in_qualification(monkeypatch, status, scoped):
    db = Database([{'job_id': '1', 'latest_job_id': 'live-99'}])
    monkeypatch.setattr(job_manager, 'supabase', db)
    events = []
    monkeypatch.setattr(job_manager, '_linkedin_request_gate', SimpleNamespace(
        acquire=lambda *a: 'grant', finish=lambda *a: events.append(a)))
    client_class = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text='upstream error'))
    monkeypatch.setattr(job_manager.httpx, 'AsyncClient', lambda: client_class(transport=transport))
    if scoped:
        with pytest.raises(RuntimeError, match='activity check failed'):
            asyncio.run(job_manager.check_linkedin_job_activity(job_id='1', limit=1))
        assert len(db.calls) == 1
    else:
        asyncio.run(job_manager.check_linkedin_job_activity())
        assert len(db.calls) == 2
        assert set(db.calls[1].payload) == {'last_checked'}
    assert events == [('grant', 'http_error', status)]


class Query:
    def __init__(self, db):
        self.db = db
        self.ops = []
        self.payload = None
    @property
    def not_(self):
        self.ops.append(('not',))
        return self
    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.ops.append((name, *args))
            if name == 'update':
                self.payload = args[0]
            return self
        return call
    def execute(self):
        self.db.calls.append(self)
        if self.db.fail:
            raise RuntimeError('offline API failure')
        if self.payload is not None:
            if self.db.update_fail:
                raise RuntimeError('offline update failure')
            return SimpleNamespace(data=self.db.update_rows)
        return SimpleNamespace(data=self.db.rows)

class Database:
    def __init__(self, rows, fail=False, *, update_rows=None, update_fail=False):
        self.rows, self.fail, self.calls = rows, fail, []
        self.update_rows = rows if update_rows is None else update_rows
        self.update_fail = update_fail
    def table(self, name):
        return Query(self)

@pytest.mark.parametrize('method', ['mark_expired_jobs', 'check_linkedin_job_activity'])
def test_scoped_manager_refuses_oversized_selection_before_any_http_or_update(monkeypatch, method):
    db = Database([{'job_id': '1'}, {'job_id': '2'}])
    monkeypatch.setattr(job_manager, 'supabase', db)
    with pytest.raises(RuntimeError, match='envelope'):
        asyncio.run(getattr(job_manager, method)(job_id='1', limit=1))
    assert len(db.calls) == 1
    assert ('eq', 'job_id', '1') in db.calls[0].ops
    assert ('limit', 1) in db.calls[0].ops


def test_scoped_expiry_updates_only_selected_id_with_protection_rechecked(monkeypatch):
    db = Database([{'job_id': '1'}])
    monkeypatch.setattr(job_manager, 'supabase', db)
    asyncio.run(job_manager.mark_expired_jobs(job_id='1', limit=1))
    assert len(db.calls) == 2
    update = db.calls[1]
    assert update.payload == {'job_state': 'expired', 'is_active': False}
    assert ('in_', 'job_id', ['1']) in update.ops
    assert ('in_', 'status', ['applied', 'offer', 'interviewing']) in update.ops
    assert ('eq', 'is_active', True) in update.ops
    assert any(op[0:2] == ('lt', 'last_seen_at') for op in update.ops)

@pytest.mark.parametrize('method', ['mark_expired_jobs', 'check_linkedin_job_activity'])
def test_scoped_manager_propagates_api_failure(monkeypatch, method):
    monkeypatch.setattr(job_manager, 'supabase', Database([], fail=True))
    with pytest.raises(RuntimeError, match='offline API failure'):
        asyncio.run(getattr(job_manager, method)(job_id='1', limit=1))

@pytest.mark.parametrize('method', ['mark_expired_jobs', 'check_linkedin_job_activity'])
def test_scoped_manager_rejects_invalid_bounds_before_query(monkeypatch, method):
    db = Database([])
    monkeypatch.setattr(job_manager, 'supabase', db)
    for kwargs in ({'limit': 1}, {'job_id': '1'}, {'job_id': '1', 'limit': 0}, {'job_id': '1', 'limit': True}):
        with pytest.raises(ValueError):
            asyncio.run(getattr(job_manager, method)(**kwargs))
    assert not db.calls


def test_qualification_runner_calls_both_real_manager_operations_with_explicit_ids(monkeypatch):
    from scripts.run_workflow_qualification import execute
    calls = []
    async def expiry(**kw): calls.append(('expiry', kw))
    async def activity(**kw): calls.append(('activity', kw))
    monkeypatch.setenv('QUALIFICATION_EXPIRY_JOB_ID', 'expired-1')
    monkeypatch.setenv('QUALIFICATION_ACTIVITY_JOB_ID', 'live-2')
    execute('job_manager', 'technology_delivery', importer=lambda name: SimpleNamespace(
        mark_expired_jobs=expiry, check_linkedin_job_activity=activity))
    assert calls == [('expiry', {'job_id': 'expired-1', 'limit': 1}), ('activity', {'job_id': 'live-2', 'limit': 1})]


def test_qualification_runner_rejects_missing_manager_ids_before_import(monkeypatch):
    from scripts.run_workflow_qualification import execute
    monkeypatch.delenv('QUALIFICATION_EXPIRY_JOB_ID', raising=False)
    monkeypatch.delenv('QUALIFICATION_ACTIVITY_JOB_ID', raising=False)
    with pytest.raises(ValueError, match='explicit'):
        execute('job_manager', 'technology_delivery', importer=lambda name: pytest.fail('imported without scope'))


@pytest.mark.parametrize('operation', ['expiry', 'active', 'inactive'])
@pytest.mark.parametrize('failure', ['empty_selection', 'empty_update', 'update_api'])
def test_scoped_manager_requires_actual_guarded_write(monkeypatch, operation, failure):
    db = Database([] if failure == 'empty_selection' else [{'job_id': '1'}],
                  update_rows=[] if failure == 'empty_update' else None,
                  update_fail=failure == 'update_api')
    monkeypatch.setattr(job_manager, 'supabase', db)
    async def check(*args, **kwargs):
        return operation == 'inactive'
    monkeypatch.setattr(job_manager, '_check_single_linkedin_job_active', check)
    method = job_manager.mark_expired_jobs if operation == 'expiry' else job_manager.check_linkedin_job_activity
    with pytest.raises(RuntimeError, match='qualification|offline update failure'):
        asyncio.run(method(job_id='1', limit=1))
    assert len(db.calls) == (1 if failure == 'empty_selection' else 2)


def test_qualification_runner_rejects_identical_manager_ids_before_import(monkeypatch):
    from scripts.run_workflow_qualification import execute
    monkeypatch.setenv('QUALIFICATION_EXPIRY_JOB_ID', 'same-id')
    monkeypatch.setenv('QUALIFICATION_ACTIVITY_JOB_ID', 'same-id')
    with pytest.raises(ValueError, match='distinct'):
        execute('job_manager', 'technology_delivery', importer=lambda name: pytest.fail('imported identical scope'))


@pytest.mark.parametrize('inactive', [True, False, None])
def test_scoped_activity_only_updates_selected_canonical_row_or_fails_closed(monkeypatch, inactive):
    db = Database([{'job_id': '1', 'latest_job_id': 'live-99'}])
    monkeypatch.setattr(job_manager, 'supabase', db)
    async def check(live_id, client, **kwargs):
        assert live_id == 'live-99'
        return inactive
    monkeypatch.setattr(job_manager, '_check_single_linkedin_job_active', check)
    if inactive is None:
        with pytest.raises(RuntimeError, match='activity check failed'):
            asyncio.run(job_manager.check_linkedin_job_activity(job_id='1', limit=1))
        assert len(db.calls) == 1
    else:
        asyncio.run(job_manager.check_linkedin_job_activity(job_id='1', limit=1))
        assert len(db.calls) == 2
        update = db.calls[1]
        assert ('in_', 'job_id', ['1']) in update.ops
        assert ('in_', 'status', ['applied', 'offer', 'interviewing']) in update.ops
        assert ('eq', 'provider', 'linkedin') in update.ops
        assert ('eq', 'is_active', True) in update.ops
        assert 'last_checked' in update.payload
        assert (update.payload.get('job_state') == 'removed') is inactive
