"""Offline native-contract replay; never initializes production credentials.

Set LINKEDIN_BOUNDARY_NATIVE_REPLAY to the protected frozen qualification JSON
for the full actual-configuration replay. No credentials or replay are committed.
"""
import copy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE_CONFIG_SHA256 = '0901bf42ef1c089cbdc4abf5816c6dcf6a27ce0809f0d2cd635d5e6219f68515'
ORIGINAL_ANCHOR = datetime.fromisoformat('2026-08-07T20:49:36.259178+00:00')


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('network forbidden'))
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('JOB_DATA_API_URL', 'https://data.test')
    monkeypatch.setenv('JOB_DATA_API_TOKEN', 'inert-token')
    import linkedin_boundary_probe
    return linkedin_boundary_probe


@pytest.fixture
def native_config(probe):
    replay = os.environ.get('LINKEDIN_BOUNDARY_NATIVE_REPLAY')
    if not replay:
        pytest.skip('protected frozen native replay not supplied')
    raw = json.loads(Path(replay).read_text())['configuration']
    assert probe.config_digest(raw) == NATIVE_CONFIG_SHA256
    assert raw['settings']['options'] == {}
    return raw


def runner_args(probe, tmp_path):
    import user_agents
    return SimpleNamespace(
        authorization=probe.AUTHORIZATION, expected_endpoint='https://data.test',
        expected_config_sha256=NATIVE_CONFIG_SHA256,
        expected_user_agent_sha256=hashlib.sha256(user_agents.USER_AGENTS[0].encode()).hexdigest(),
        output=str(tmp_path / 'evidence'))


def test_native_empty_options_passes_full_parent_validation_before_get(probe, native_config, monkeypatch, tmp_path):
    import httpx
    from scrape_configuration import parse_scrape_configuration, build_search_executions
    original = probe.originals()
    targets_bytes = (ROOT / 'recovery_parameters.json').read_bytes()
    targets = json.loads(targets_bytes)
    definitions = [original.scope_definition(e, original.LINKEDIN_JOB_TYPE, original.LINKEDIN_F_WT)
                   for e in build_search_executions(parse_scrape_configuration(native_config))]
    probe.verify_targets(targets, definitions)
    assert len(definitions) == 13
    assert sum(len(t['original_gap_intervals']) for t in targets) == 39
    before = copy.deepcopy(native_config)
    events = []

    def data_send(client, request, **kw):
        assert request.url.path == '/rest/v1/rpc/get_scraper_configuration'
        events.append('configuration')
        return httpx.Response(200, json=native_config, request=request)

    class ReachedCapture(Exception):
        pass

    def capture(*args):
        events.append('capture')
        assert args[4].attempts == 0
        raise ReachedCapture

    monkeypatch.setattr(httpx.Client, 'send', data_send)
    monkeypatch.setattr(probe, 'capture', capture)
    with pytest.raises(ReachedCapture):
        probe.run(runner_args(probe, tmp_path))
    assert events == ['configuration', 'capture']
    assert native_config == before
    assert (ROOT / 'recovery_parameters.json').read_bytes() == targets_bytes
    assert json.loads((tmp_path / 'evidence/actual-configuration.json').read_text()) == native_config


@pytest.mark.parametrize('singleton_rpc_envelopes', [False, True])
def test_original_anchor_at_nov5_accepts_full_native_replay_without_narrowing(probe, native_config, monkeypatch, tmp_path, singleton_rpc_envelopes):
    import httpx
    import requests
    from urllib.parse import parse_qs, urlsplit
    events, urls, send_times = [], [], []
    clock = [1000.0]
    started_at = datetime.fromisoformat('2026-11-05T21:57:46.758591+00:00')
    targets_bytes = (ROOT / 'recovery_parameters.json').read_bytes()

    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/', 1)[-1]
        events.append(name)
        values = {'get_scraper_configuration': native_config,
                  'acquire_linkedin_request_grant': {'outcome': 'grant', 'grant_id': str(len(events))},
                  'consume_linkedin_request_grant': {'consumed': True, 'started_at': started_at.isoformat()},
                  'finish_linkedin_request_grant': True}
        value = values[name]
        if singleton_rpc_envelopes and isinstance(value, dict):
            value = [value]
        return httpx.Response(200, json=value, request=request)

    def source_send(adapter, request, **kw):
        assert events[-1] == 'consume_linkedin_request_grant'
        urls.append(request.url)
        send_times.append(clock[0])
        params = parse_qs(urlsplit(request.url).query)
        assert params['f_TPR'] == [f'r{probe.math.ceil((started_at - ORIGINAL_ANCHOR).total_seconds())}']
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        response._content = b'<li><div class="base-card" data-entity-urn="urn:li:jobPosting:123"></div></li>'
        return response

    monkeypatch.setattr(httpx.Client, 'send', data_send)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', source_send)
    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(probe.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    probe.run(runner_args(probe, tmp_path))
    assert probe.ANCHOR == ORIGINAL_ANCHOR
    assert len(urls) == len(probe.plan()) == 12
    assert all(b - a >= 2.5 for a, b in zip(send_times, send_times[1:]))
    assert len(events) == 37
    output = tmp_path / 'evidence'
    assert (output / 'full-targets.json').read_bytes() == targets_bytes
    summary = json.loads((output / 'summary.json').read_text())
    assert (summary['all_parent_count'], summary['original_interval_count'], summary['physical_gets']) == (13, 39, 12)
    assert summary['configuration_sha256'] == NATIVE_CONFIG_SHA256
    assert summary['inventory_complete'] is False
    receipts = [json.loads(p.read_text()) for p in output.glob('*.json') if p.name[:2].isdigit()]
    assert len(receipts) == 12
    assert all(r['source_anchor'] == ORIGINAL_ANCHOR.isoformat() and r['parsed_ids'] == ['123'] for r in receipts)


@pytest.mark.parametrize('delta', [timedelta(hours=2400), timedelta(hours=2400, microseconds=1)])
def test_reviewed_diagnostic_horizon_exact_ceiling(probe, monkeypatch, tmp_path, delta):
    import requests
    target = json.loads((ROOT / 'recovery_parameters.json').read_text())[0]
    finishes, sends = [], []
    gate = SimpleNamespace(
        acquire=lambda *a, **kw: SimpleNamespace(grant_id='g', started_at=ORIGINAL_ANCHOR + delta),
        finish=lambda *a: finishes.append(a))

    def send(adapter, request, **kw):
        sends.append(request.url)
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response._content = b'<li><div class="base-card" data-entity-urn="urn:li:jobPosting:123"></div></li>'
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    with probe.Boundary('https://data.test') as boundary:
        if delta > timedelta(hours=2400):
            with pytest.raises(RuntimeError, match='2400-hour'):
                probe.capture(target, 'baseline', 240, gate, boundary, probe.originals(), tmp_path, 'ua')
            assert boundary.attempts == 0 and not sends
            assert finishes[0][1] == 'window_expired'
        else:
            result = probe.capture(target, 'baseline', 240, gate, boundary, probe.originals(), tmp_path, 'ua')
            assert result['query_params']['f_TPR'] == 'r8640000'
            assert boundary.attempts == len(sends) == 1
