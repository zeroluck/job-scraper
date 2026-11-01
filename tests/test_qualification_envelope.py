"""Offline contracts; RPC state doubles do not qualify a live PostgreSQL authority."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE_TABLES = {'linkedin_source_request_policy', 'linkedin_source_request_grants',
               'linkedin_discovery_task_attempts'}


def test_matrix_covers_shared_gate_side_effects_without_job_scoping():
    matrix = json.loads((ROOT / 'docs/workflow-qualification-matrix.json').read_text())
    assert len(matrix['workflows']) == matrix['workflow_count'] == 12
    for name in ('backfill_linkedin_metadata', 'job_manager', 'scrape_jobs'):
        item = next(w for w in matrix['workflows'] if w['path'].endswith('/' + name + '.yml'))
        assert GATE_TABLES <= set(item['readback']['tables'])
        for table in GATE_TABLES:
            statement = next(s for s in item['readback']['fingerprint_sql'].split(';') if 'FROM public.' + table + ' t' in s)
            assert 'job_id' not in statement and 'lane' not in statement
        gate = item['request_gate_envelope']
        assert gate['scope'] == 'shared_linkedin_source'
        assert gate['automatic_circuit_reset'] is False
        assert gate['challenge_invalidates_other_producers'] is True
        assert 'expired' in gate['acceptance'] and 'finished' in gate['acceptance']
    for name in ('freehire_compat', 'backfill_linkedin_metadata', 'backfill_same_id_relists'):
        item = next(w for w in matrix['workflows'] if w['path'].endswith('/' + name + '.yml'))
        assert item['selection_scope'] == 'one_global_canonical_candidate_not_lane_filtered'
    analysis = next(w for w in matrix['workflows'] if w['path'].endswith('/analyze_jobs.yml'))
    assert 'job_keyword_insights' in analysis['readback']['tables']
    assert 'job_keyword_facts' not in analysis['readback']['tables']
    for item in matrix['workflows']:
        if 'jobs' in item.get('readback', {}).get('tables', []):
            assert 'canonical_provider_revisions' in item['readback']['tables']


def test_actual_llm_clients_share_failed_call_retry_and_fallback_budget(monkeypatch):
    import llm_client
    from scripts.run_workflow_qualification import bounded_completion
    seen = []
    def transport(**kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            raise RuntimeError('503 offline provider unavailable')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='ok'))])
    monkeypatch.setattr(llm_client.time, 'sleep', lambda _: None)
    monkeypatch.setattr(llm_client.litellm, 'completion', bounded_completion(transport))
    first = llm_client.LLMClient('offline/first', max_retries=3, model_chain=['offline/first', 'offline/fallback'])
    second = llm_client.LLMClient('offline/second', max_retries=3)
    assert first.generate_content('bounded', max_tokens=99999) == 'ok'
    with pytest.raises(RuntimeError, match='qualification request budget exhausted'):
        second.generate_content('bounded')
    assert [c['model'] for c in seen] == ['offline/first', 'offline/fallback']
    assert all(c['num_retries'] == 0 and c['max_tokens'] == 4096 and c['timeout'] == 30 for c in seen)


class GateRPCState:
    """In-memory RPC boundary, intentionally not a PostgreSQL implementation test."""
    def __init__(self):
        self.policy = {'circuit_state': 'closed', 'circuit_generation': 0, 'next_allowed_at': 0}
        self.grants = {'unrelated-expired': {'status': 'pending'},
                       'unrelated-live': {'status': 'consumed'}}
        self.attempts = {'unrelated-live': {'response_class': 'started'}}
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        def execute():
            if name == 'acquire_linkedin_request_grant':
                self.grants['unrelated-expired']['status'] = 'expired'
                if self.policy['circuit_state'] == 'open':
                    return SimpleNamespace(data={'outcome': 'circuit_open'})
                key = params['p_request_key']
                self.grants[key] = {'status': 'consumed', 'producer': params['p_producer']}
                self.policy['next_allowed_at'] += 1
                value = {'outcome': 'grant', 'consumed': True, 'grant_id': key,
                         'started_at': '2026-01-01T00:00:00+00:00'}
            elif name == 'finish_linkedin_request_grant':
                self.grants[params['p_grant_id']].update(
                    status='finished', response_class=params['p_response_class'], http_status=params['p_http_status'])
                value = True
            elif name == 'open_linkedin_source_circuit':
                self.policy.update(circuit_state='open', circuit_generation=1)
                for grant in self.grants.values():
                    if grant['status'] in ('consumed', 'pending'):
                        grant.update(status='invalidated', response_class='invalidated')
                self.grants[params['p_grant_id']].update(response_class='challenge')
                self.attempts['unrelated-live']['response_class'] = 'invalidated'
                value = True
            else:
                raise AssertionError(name)
            return SimpleNamespace(data=value)
        return SimpleNamespace(execute=execute)


@pytest.mark.parametrize('statuses,classes', [
    ([200], ['complete']), ([503, 503, 503, 200], ['http_error'] * 3 + ['complete']),
    ([404, 404], ['not_found_unconfirmed', 'terminal_unavailable']),
    ([403], ['challenge']), ([503] * 4, ['http_error'] * 4),
])
def test_actual_metadata_qualification_path_reads_gate_effects(monkeypatch, statuses, classes):
    import requests
    import scraper
    import supabase_utils
    import backfill_linkedin_metadata as worker
    from scripts.run_workflow_qualification import execute
    from linkedin_source_policy import LinkedInCircuitOpen
    state = GateRPCState()
    monkeypatch.setattr(supabase_utils, 'supabase', state)
    monkeypatch.setattr(worker, 'fetch_candidates', lambda limit: [{'job_id': 'canonical', 'latest_job_id': 'source'}] if limit == 1 else pytest.fail('unbounded selection'))
    monkeypatch.setattr(scraper.time, 'sleep', lambda _: None)
    writes = []
    class Update:
        def update(self, payload):
            self.payload = payload
            return self
        def eq(self, field, value):
            assert (field, value) == ('job_id', 'canonical')
            return self
        def execute(self):
            writes.append(self.payload)
            return SimpleNamespace(data=[self.payload])
    state.table = lambda table: Update()
    responses = iter(statuses)
    http_calls = []
    def http_get(url, **kwargs):
        http_calls.append(url)
        response = requests.Response()
        response.status_code = next(responses)
        response.url = url
        response._content = (ROOT / 'tests/fixtures/linkedin_job_detail_recruiter.html').read_bytes()
        return response
    monkeypatch.setattr(scraper.requests, 'get', http_get)
    # Real runner -> real worker -> real parser/gate -> real SDK helper -> RPC double.
    if statuses == [403]:
        with pytest.raises(LinkedInCircuitOpen):
            execute('backfill_linkedin_metadata', 'technology_delivery')
    elif statuses == [503] * 4:
        with pytest.raises(scraper.LinkedInRequestFailed, match='exhausted retries'):
            execute('backfill_linkedin_metadata', 'technology_delivery')
    else:
        result = execute('backfill_linkedin_metadata', 'technology_delivery')
        assert result['checked'] == 1
        assert len(writes) == 1
        assert result['updated'] == (0 if statuses == [404, 404] else 1)
        if statuses != [404, 404]:
            assert writes[0]['applicant_count'] == 26
            assert writes[0]['salary_min'] == 120000
    grants = [g for key, g in state.grants.items() if key.startswith('source:')]
    assert len(http_calls) == len(grants) == len(statuses)
    assert [g['response_class'] for g in grants] == classes
    assert state.grants['unrelated-expired']['status'] == 'expired'
    assert state.policy['next_allowed_at'] == len(statuses)
    if statuses == [403]:
        assert not writes
        assert state.policy['circuit_state'] == 'open'
        assert state.policy['circuit_generation'] == 1
        assert state.grants['unrelated-live']['status'] == 'invalidated'
        assert state.attempts['unrelated-live']['response_class'] == 'invalidated'
    else:
        assert state.policy['circuit_state'] == 'closed'
        assert state.grants['unrelated-live']['status'] == 'consumed'


@pytest.mark.parametrize('error', [RuntimeError, SystemExit])
def test_main_failure_emits_sanitized_attempt_diagnostics(monkeypatch, capsys, error):
    from scripts import run_workflow_qualification as runner
    import litellm
    monkeypatch.setenv('JOB_DATA_API_URL', 'https://api.example.test')
    monkeypatch.setenv('JOB_DATA_API_TOKEN', 'offline-token')
    monkeypatch.setattr(runner, 'install_deadline', lambda: None)
    def transport(**kwargs):
        raise error('private credential-bearing transport detail')
    monkeypatch.setattr(litellm, 'completion', transport)
    def worker(*args):
        litellm.completion(messages=[])
    monkeypatch.setattr(runner, 'execute', worker)
    assert runner.main(['--workflow', 'analyze_jobs', '--archetype', 'technology_delivery']) == 1
    output = capsys.readouterr()
    receipt = json.loads(output.err)
    assert receipt['execution_returned'] is False
    assert receipt['readback_required'] is True
    assert receipt['error_type'] == error.__name__
    assert receipt['llm_attempts'] == 1
    assert 'private credential' not in output.err
    assert litellm.completion is transport
