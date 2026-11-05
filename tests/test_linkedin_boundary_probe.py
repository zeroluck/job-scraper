"""Offline only: transport sends intercepted; sockets denied before imports."""
import importlib.util
from pathlib import Path
import socket
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_probe_requires_explicit_authorization_before_transport(monkeypatch, tmp_path):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    path = ROOT / 'linkedin_boundary_probe.py'
    assert path.exists(), 'evidence-only probe is missing'
    spec = importlib.util.spec_from_file_location('linkedin_boundary_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match='authorization'):
        module.require_authorization('')


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    import linkedin_boundary_probe as p
    return p


def test_one_get_uses_real_gate_and_classifiers_at_http_boundary(probe, monkeypatch, tmp_path):
    import httpx
    import requests
    from types import SimpleNamespace
    events = []
    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/', 1)[-1]
        events.append(name)
        assert name in probe.RPCS
        values = {'acquire_linkedin_request_grant': {'outcome': 'grant', 'grant_id': 'fixture-grant'},
                  'consume_linkedin_request_grant': {'consumed': True, 'started_at': '2026-11-05T00:00:00+00:00'},
                  'finish_linkedin_request_grant': True}
        return httpx.Response(200, json=values[name], request=request)
    monkeypatch.setattr(httpx.Client, 'send', data_send)
    def source_send(adapter, request, **kw):
        assert events[-1] == 'consume_linkedin_request_grant'
        events.append('GET')
        assert request.method == 'GET'
        assert request.headers['User-Agent'] == 'original-agent'
        assert kw['timeout'] <= 120
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.headers = {'Content-Type': 'text/html', 'Set-Cookie': 'secret'}
        response._content = b'<li><div class="base-card" data-entity-urn="urn:li:jobPosting:123"></div><time datetime="2026-09-15">old</time></li><a href="/jobs/view/title-456">extra</a>'
        return response
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', source_send)
    from data_client import create_data_client
    monkeypatch.setenv('JOB_DATA_API_URL', 'https://data.test')
    monkeypatch.setenv('JOB_DATA_API_TOKEN', 'inert-token')
    db = create_data_client()
    with probe.Boundary('https://data.test', 120) as boundary:
        originals = probe.originals()
        gate = originals.DurableLinkedInRequestGate('source-boundary-evidence', db=db)
        target = __import__('json').loads((ROOT / 'recovery_parameters.json').read_text())[0]
        result = probe.capture(target, 'baseline', 240, gate, boundary, originals, tmp_path, 'original-agent')
    assert events == ['acquire_linkedin_request_grant', 'consume_linkedin_request_grant', 'GET', 'finish_linkedin_request_grant']
    assert result['raw_urn_ids'] == ['123']
    assert result['raw_link_ids'] == ['456']
    assert result['parsed_ids'] == ['123']
    assert result['dates'][0]['datetime'] == '2026-09-15'
    assert 'Set-Cookie' not in result['headers']
    assert result['scope_parent_hash'] == target['scope_key'].rsplit(':', 1)[1]
    assert boundary.attempts == 1
    assert (tmp_path / result['body_path']).stat().st_mode & 0o777 == 0o600


def test_manifest_rejects_missing_intervals_and_changed_scope(probe):
    import json, copy
    targets = json.loads((ROOT / 'recovery_parameters.json').read_text())
    definitions = [t['definition'] for t in targets]
    probe.verify_targets(targets, definitions)
    for mutate in ('parent', 'interval', 'query', 'duplicate', 'wire'):
        changed = copy.deepcopy(targets)
        if mutate == 'parent': changed.pop()
        if mutate == 'interval': changed[0]['original_gap_intervals'].pop()
        if mutate == 'query': changed[0]['definition']['query'] += ' narrower'
        if mutate == 'duplicate': changed[-1] = changed[0]
        if mutate == 'wire': changed[0]['query_params']['f_WT'] = '2'
        with pytest.raises(RuntimeError):
            probe.verify_targets(changed, definitions)


def test_plan_is_exact_sentinel_then_diagnostic_variants(probe):
    assert probe.plan() == [('baseline', n) for n in (240,250,260,300,240)] + [('DD', n) for n in (0,240,250,260,300)] + [('baseline',0),('interactive',0)]


@pytest.mark.parametrize('method,url', [
    ('GET', 'https://data.test/rest/v1/jobs'),
    ('POST', 'https://data.test/rest/v1/rpc/prepare_linkedin_discovery_scope_state'),
    ('POST', 'https://other.test/rest/v1/rpc/acquire_linkedin_request_grant'),
    ('POST', 'https://data.test/rest/v1/rpc/reset_linkedin_source_circuit')])
def test_data_http_boundary_denies_unauthorized_calls(probe, method, url):
    import httpx
    with probe.Boundary('https://data.test'):
        with pytest.raises(RuntimeError, match='unauthorized data'):
            httpx.Client().request(method, url)


@pytest.mark.parametrize('method,url', [
    ('GET', 'https://www.linkedin.com' + '/jobs/search'),
    ('POST', 'https://www.linkedin.com/jobs/search'),
    ('GET', 'https://other.test/jobs/search')])
def test_no_source_http_without_one_shot_consumed_grant(probe, method, url):
    import requests
    with probe.Boundary('https://data.test'):
        with pytest.raises(RuntimeError, match='unauthorized source'):
            requests.request(method, url)


@pytest.mark.parametrize('status,body', [
    (429,b'<li></li>'), (503,b'<li></li>'), (302,b''),
    (403,b'<title>Security Verification</title>'),
    (200,b'<div>unknown</div>'),
    (200,b'<section class="no-results"></section><a href="/jobs/view/title-456">hidden</a>')])
def test_source_interruptions_have_one_send_no_retry(probe, monkeypatch, tmp_path, status, body):
    import requests
    from types import SimpleNamespace
    events = []
    original = probe.originals()
    class Gate:
        def acquire(self, *a, **kw):
            events.append('consume')
            return SimpleNamespace(grant_id='g', started_at=probe.datetime.fromisoformat('2026-11-05T00:00:00+00:00'))
        def finish(self, *a): events.append('finish')
        def open_circuit(self, *a): events.append('circuit')
    def send(adapter, request, **kw):
        events.append('GET')
        r = requests.Response(); r.status_code = status; r._content = body; r.url = request.url; r.request = request
        r.headers['Location'] = 'https://other.test/'
        return r
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    target = __import__('json').loads((ROOT / 'recovery_parameters.json').read_text())[0]
    with probe.Boundary('https://data.test') as boundary:
        with pytest.raises(RuntimeError):
            probe.capture(target,'baseline',250,Gate(),boundary,original,tmp_path,'ua')
        assert boundary.attempts == 1
    assert events == ['consume','GET', 'circuit' if status == 403 else 'finish']
    assert list(tmp_path.glob('*.body'))


def test_budget_and_expired_deadline_prevent_acquire(probe, tmp_path):
    original = probe.originals()
    from types import SimpleNamespace
    def forbidden(*a, **kw): pytest.fail('grant after exhaustion')
    gate = SimpleNamespace(acquire=forbidden)
    for expired in (False,True):
        with probe.Boundary('https://data.test',limit=0 if not expired else 20) as b:
            if expired: b.deadline = probe.time.monotonic() - 1
            with pytest.raises(RuntimeError):
                probe.capture({},'baseline',240,gate,b,original,tmp_path,'ua')


def test_full_runner_uses_all_config_then_12_exact_requests(probe, monkeypatch, tmp_path):
    """Synthetic configuration for offline wiring, never production configuration evidence."""
    import json, httpx, requests, user_agents, hashlib
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('fixture_config', ROOT/'tests/test_scrape_configuration.py')
    fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
    raw = fixtures.rpc_payload()
    targets = json.loads((ROOT/'recovery_parameters.json').read_text())
    for lane in raw['lanes']:
        matches = [t['definition'] for t in targets if t['definition']['lane'] == lane['archetype']]
        lane['enabled'] = bool(matches)
        if matches:
            lane['queries'] = [dict(archetype=lane['archetype'], query=d['query'],query_type=d['query_type'],language=d['language'],enabled=True,sort_order=i) for i,d in enumerate(matches)]
    raw['settings']['options']['global_request_interval_ms'] = 2500
    events, urls = [], []
    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/',1)[-1]; events.append(name)
        assert name in probe.RPCS
        values = {'get_scraper_configuration': raw,
                  'acquire_linkedin_request_grant': {'outcome':'grant','grant_id':str(len(events))},
                  'consume_linkedin_request_grant': {'consumed':True,'started_at':'2026-11-05T00:00:00+00:00'},
                  'finish_linkedin_request_grant':True}
        return httpx.Response(200,json=values[name],request=request)
    def source_send(adapter,request,**kw):
        assert events[-1] == 'consume_linkedin_request_grant'
        urls.append(request.url)
        r=requests.Response(); r.status_code=200; r.url=request.url; r.request=request
        r._content=b'<li><div class="base-card" data-entity-urn="urn:li:jobPosting:123"></div></li>'
        return r
    monkeypatch.setattr(httpx.Client,'send',data_send)
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',source_send)
    clock=[1000.0]
    monkeypatch.setattr(probe.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(probe.time,'sleep',lambda n:clock.__setitem__(0,clock[0]+n))
    monkeypatch.setenv('JOB_DATA_API_URL','https://data.test')
    monkeypatch.setenv('JOB_DATA_API_TOKEN','inert-token')
    args=SimpleNamespace(authorization=probe.AUTHORIZATION,expected_endpoint='https://data.test',
        expected_config_sha256=probe.config_digest(raw),expected_user_agent_sha256=hashlib.sha256(user_agents.USER_AGENTS[0].encode()).hexdigest(),output=str(tmp_path/'evidence'))
    probe.run(args)
    assert len(urls)==12
    assert len(events)==37
    assert clock[0] >= 1027.5
    summary=json.loads((tmp_path/'evidence/summary.json').read_text())
    assert summary['all_parent_count']==13 and summary['original_interval_count']==39
    assert len(summary['remaining_parents'])==12
    assert summary['inventory_complete'] is False
    for path in (tmp_path/'evidence').glob('*.json'):
        receipt=json.loads(path.read_text())
        if 'body_path' in receipt:
            assert hashlib.sha256((path.parent/receipt['body_path']).read_bytes()).hexdigest()==receipt['body_sha256']


def test_manual_workflow_has_no_storage_or_llm_secrets(probe):
    import yaml
    text=(ROOT/'.github/workflows/linkedin_boundary_probe_manual.yml').read_text()
    workflow=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    assert workflow['concurrency']=={'group':'linkedin-freehire-pipeline','cancel-in-progress':'false'}
    assert 'SUPABASE_SERVICE_ROLE_KEY' not in text and 'LLM_API_KEY' not in text
    assert 'retention-days: 7' in text


def test_manual_workflow_encrypts_only_for_validated_public_recipient():
    import yaml
    import os
    import subprocess
    import tempfile
    text = (ROOT / '.github/workflows/linkedin_boundary_probe_manual.yml').read_text()
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    recipient = workflow['on']['workflow_dispatch']['inputs']['recipient_cert_b64']
    assert recipient['required'] == 'true' and recipient['type'] == 'string'
    assert 'repository.private' not in text
    steps = workflow['jobs']['evidence']['steps']
    validation = next(s for s in steps if s.get('id') == 'recipient')
    probe_index = next(i for i, s in enumerate(steps) if 'python linkedin_boundary_probe.py' in s.get('run', ''))
    assert steps.index(validation) < probe_index
    assert validation['env']['RECIPIENT_CERT_B64'] == '${{ inputs.recipient_cert_b64 }}'
    assert 'umask 077' in validation['run']
    assert 'openssl x509' in validation['run']
    assert 'validate=True' in validation['run']
    package = next(s for s in steps if 'tar -czf' in s.get('run', ''))
    assert "steps.recipient.outcome == 'success'" in package['if']
    assert 'openssl cms -encrypt -binary -aes-256-cbc -outform DER' in package['run']
    assert '.tar.gz.cms' in package['run']
    uploads = [s for s in steps if s.get('uses', '').startswith('actions/upload-artifact@')]
    assert len(uploads) == 1
    assert uploads[0]['with']['path'] == '${{ runner.temp }}/linkedin-boundary-evidence.tar.gz.cms'
    assert uploads[0]['with']['retention-days'] == '7'
    # Execute the actual validation shell, not a reimplementation; malformed input
    # must fail closed before any probe, with no ciphertext made available.
    for invalid in ('', 'not-base64!', 'bm90IGEgY2VydGlmaWNhdGU='):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', validation['run']],
                                    env={**os.environ, 'RUNNER_TEMP': directory, 'RECIPIENT_CERT_B64': invalid},
                                    capture_output=True, text=True)
            assert result.returncode != 0
            assert not list(Path(directory).glob('*.cms'))


@pytest.mark.parametrize('outcome', ['circuit_open','wait','consume_circuit'])
def test_original_gate_denial_stops_before_http_get(probe, monkeypatch, tmp_path, outcome):
    import httpx, requests, json
    from data_client import create_data_client
    calls=[]
    def send(client,request,**kw):
        name=request.url.path.rsplit('/',1)[-1]; calls.append(name)
        if name=='acquire_linkedin_request_grant':
            data={'outcome':'grant','grant_id':'g'} if outcome=='consume_circuit' else {'outcome':outcome,'wait_ms':60000}
        else:
            assert name=='consume_linkedin_request_grant'
            data={'consumed':False,'reason':'circuit_open'}
        return httpx.Response(200,json=data,request=request)
    monkeypatch.setattr(httpx.Client,'send',send)
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda *a,**kw:pytest.fail('source GET after denied grant'))
    monkeypatch.setenv('JOB_DATA_API_URL','https://data.test'); monkeypatch.setenv('JOB_DATA_API_TOKEN','inert-token')
    original=probe.originals(); gate=original.DurableLinkedInRequestGate('evidence-test',db=create_data_client())
    with probe.Boundary('https://data.test',seconds=1) as b:
        with pytest.raises((original.LinkedInCircuitOpen,original.LinkedInRequestDeadlineExceeded)):
            probe.capture(json.loads((ROOT/'recovery_parameters.json').read_text())[0],'baseline',240,gate,b,original,tmp_path,'ua')
        assert b.attempts==0
    assert not list(tmp_path.iterdir())


def test_nested_source_retries_are_rejected_before_adapter_send(probe, monkeypatch):
    import requests
    session=requests.Session()
    session.mount('https://',requests.adapters.HTTPAdapter(max_retries=3))
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda *a,**kw:pytest.fail('nested retry adapter reached'))
    url='https://www.linkedin.com/jobs/search'
    with probe.Boundary('https://data.test') as b:
        b.permit=url
        with pytest.raises(RuntimeError,match='nested retries'):
            session.get(url)
        assert b.attempts == 0


def test_original_frozen_anchor_expires_without_source_get(probe, monkeypatch, tmp_path):
    from types import SimpleNamespace
    import json, requests
    events=[]
    gate=SimpleNamespace(acquire=lambda *a,**kw:SimpleNamespace(grant_id='g',started_at=probe.datetime.fromisoformat('2026-11-16T00:00:00+00:00')),finish=lambda *a:events.append(a))
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda *a,**kw:pytest.fail('expired anchor GET'))
    with probe.Boundary('https://data.test') as b:
        with pytest.raises(RuntimeError,match='frozen original anchor'):
            probe.capture(json.loads((ROOT/'recovery_parameters.json').read_text())[0],'baseline',240,gate,b,probe.originals(),tmp_path,'ua')
        assert b.attempts==0
    assert events[0][1]=='window_expired'
