"""Opt-in interactive diagnostic; offline transport and original native gate."""
import json
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from test_linkedin_boundary_probe_native_contract import probe, native_config, runner_args

ROOT = Path(__file__).resolve().parents[1]
OFFSETS = (0, 60, 120, 180, 240, 250, 260, 300)


def test_reviewed_mode_is_explicit_and_original_default_unchanged(probe):
    assert probe.plan('interactive-pagination') == [('interactive', n) for n in OFFSETS]
    assert probe.plan('boundary') == probe.plan()
    assert len(probe.plan()) == 12
    with pytest.raises(RuntimeError, match='mode'):
        probe.plan('alternate-filter')


@pytest.mark.parametrize('ignored_start', [False, True])
def test_interactive_full_native_runner_preserves_scope_and_exposes_overlap(
        probe, native_config, monkeypatch, tmp_path, ignored_start):
    import httpx
    import requests
    args = runner_args(probe, tmp_path)
    args.mode = 'interactive-pagination'
    events, urls = [], []
    clock = [1000.0]
    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/', 1)[-1]
        events.append(name)
        values = {'get_scraper_configuration': native_config,
                  'acquire_linkedin_request_grant': {'outcome': 'grant', 'grant_id': str(len(events))},
                  'consume_linkedin_request_grant': {'consumed': True, 'started_at': '2026-11-05T22:00:00+00:00'},
                  'finish_linkedin_request_grant': True}
        return httpx.Response(200, json=values[name], request=request)
    def source_send(adapter, request, **kw):
        assert events[-1] == 'consume_linkedin_request_grant'
        assert kw['allow_redirects'] is False if 'allow_redirects' in kw else True
        urls.append(request.url)
        offset = int(parse_qs(urlsplit(request.url).query)['start'][0])
        source_id = '123' if ignored_start else str(1000 + offset)
        r = requests.Response(); r.status_code = 200; r.url = request.url
        r._content = ('<li><div class="base-card" data-entity-urn="urn:li:jobPosting:' + source_id + '"></div><time datetime="2026-08-19">old</time></li>').encode()
        return r
    monkeypatch.setattr(httpx.Client, 'send', data_send)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', source_send)
    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(probe.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    probe.run(args)
    assert [int(parse_qs(urlsplit(url).query)['start'][0]) for url in urls] == list(OFFSETS)
    assert all(urlsplit(url).path == '/jobs/search' for url in urls)
    assert len(urls) == 8 and len(events) == 25
    assert clock[0] == 1017.5
    output = tmp_path / 'evidence'
    summary = json.loads((output / 'summary.json').read_text())
    assert (summary['all_parent_count'], summary['original_interval_count'], summary['physical_gets']) == (13, 39, 8)
    assert summary['mode'] == args.mode
    assert summary['inventory_complete'] is False
    assert len(summary['raw_id_union']) == (1 if ignored_start else 8)
    assert len(summary['pairwise_raw_id_overlap']) == 28
    assert all(pair['same_raw_id_set'] is ignored_start for pair in summary['pairwise_raw_id_overlap'])
    for i, offset in enumerate(OFFSETS):
        r = json.loads((output / f'{i:02d}-interactive-{offset}.json').read_text())
        assert r['query_params']['start'] == offset
        assert r['source_anchor'] == probe.ANCHOR.isoformat()
        assert r['dates'][0]['datetime'] == '2026-08-19'
        assert len(r['raw_urn_ids']) == 1
        assert r['inventory_complete'] is False


def test_manual_workflow_mode_choice_defaults_to_original_plan(probe):
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/linkedin_boundary_probe_manual.yml').read_text(), Loader=yaml.BaseLoader)
    mode = workflow['on']['workflow_dispatch']['inputs']['mode']
    assert mode == {'description': 'Reviewed evidence-only plan; neither mode ingests or proves completeness',
                    'type': 'choice', 'required': 'true', 'default': 'boundary',
                    'options': ['boundary', 'interactive-pagination']}
    job = workflow['jobs']['evidence']
    assert job['env']['PROBE_MODE'] == '${{ inputs.mode }}'
    step = next(s for s in job['steps'] if 'python linkedin_boundary_probe.py' in s.get('run', ''))
    assert '--mode "$PROBE_MODE"' in step['run']


@pytest.mark.parametrize('stop', ['transport', 'crash', 'budget', 'deadline', 'gate'])
def test_interactive_stops_without_retry_and_preserves_exact_accounting(probe, monkeypatch, tmp_path, stop):
    import httpx
    import requests
    from data_client import create_data_client
    events = []
    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/', 1)[-1]; events.append(name)
        values = {'acquire_linkedin_request_grant': {'outcome': 'circuit_open'} if stop == 'gate' else {'outcome': 'grant', 'grant_id': 'g'},
                  'consume_linkedin_request_grant': {'consumed': True, 'started_at': '2026-11-05T22:00:00+00:00'},
                  'finish_linkedin_request_grant': True}
        return httpx.Response(200, json=values[name], request=request)
    def send(adapter, request, **kw):
        events.append('GET')
        if stop == 'transport':
            raise requests.ConnectionError('offline fixture')
        raise RuntimeError('offline process interruption')
    monkeypatch.setattr(httpx.Client, 'send', data_send)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    original = probe.originals()
    gate = original.DurableLinkedInRequestGate('offline-interactive', db=create_data_client())
    target = json.loads((ROOT / 'recovery_parameters.json').read_text())[0]
    with probe.Boundary('https://data.test', limit=0 if stop == 'budget' else 20) as boundary:
        if stop == 'deadline': boundary.deadline = probe.time.monotonic() - 1
        with pytest.raises(RuntimeError):
            probe.capture(target, 'interactive', 60, gate, boundary, original, tmp_path, 'ua')
        assert boundary.attempts == (1 if stop in ('transport', 'crash') else 0)
    if stop in ('transport', 'crash'):
        assert events == ['acquire_linkedin_request_grant', 'consume_linkedin_request_grant', 'GET', 'finish_linkedin_request_grant']
        r = json.loads((tmp_path / '00-interactive-60.json').read_text())
        assert r['classifier'] == ('transport_error' if stop == 'transport' else 'probe_error')
        assert r['query_params']['start'] == 60
    else:
        assert events == (['acquire_linkedin_request_grant'] if stop == 'gate' else [])
        assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('view,offset', [('baseline', 60), ('DD', 180), ('interactive', 1)])
def test_interactive_offsets_do_not_enable_other_views_or_unreviewed_units(probe, tmp_path, view, offset):
    with pytest.raises(RuntimeError, match='unreviewed diagnostic unit'):
        probe.capture({}, view, offset, None, None, None, tmp_path, 'ua')


def test_invalid_mode_stops_before_config_or_source(probe, tmp_path):
    args = runner_args(probe, tmp_path)
    args.mode = 'alternate-filter'
    with pytest.raises(RuntimeError, match='mode'):
        probe.run(args)
    assert not list(tmp_path.iterdir())


def test_selected_mode_keeps_recipient_encryption_roundtrip(probe, tmp_path):
    import base64
    import os
    import subprocess
    import tarfile
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/linkedin_boundary_probe_manual.yml').read_text(), Loader=yaml.BaseLoader)
    steps = workflow['jobs']['evidence']['steps']
    validation = next(s for s in steps if s.get('id') == 'recipient')
    package = next(s for s in steps if 'tar -czf' in s.get('run', ''))
    key, cert = tmp_path / 'key.pem', tmp_path / 'cert.pem'
    def run(command, **kw):
        return subprocess.run(command, check=True, capture_output=True, **kw)
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=offline-only', '-days', '1', '-keyout', str(key), '-out', str(cert)])
    key.chmod(0o600)
    evidence = tmp_path / 'linkedin-boundary-evidence'; evidence.mkdir(mode=0o700)
    (evidence / 'summary.json').write_text('{"inventory_complete": false}\n')
    env = {**os.environ, 'RUNNER_TEMP': str(tmp_path), 'RECIPIENT_CERT_B64': base64.b64encode(cert.read_bytes()).decode()}
    try:
        run(['bash', '-e', '-o', 'pipefail', '-c', validation['run']], env=env)
        run(['bash', '-e', '-o', 'pipefail', '-c', package['run']], env=env)
        encrypted = tmp_path / 'linkedin-boundary-evidence.tar.gz.cms'
        assert encrypted.exists() and not (tmp_path / 'linkedin-boundary-evidence.tar.gz').exists()
        archive = tmp_path / 'decrypted.tar.gz'
        run(['openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER', '-in', str(encrypted), '-recip', str(cert), '-inkey', str(key), '-out', str(archive)])
        with tarfile.open(archive) as tar:
            assert tar.extractfile('linkedin-boundary-evidence/summary.json').read() == (evidence / 'summary.json').read_bytes()
    finally:
        key.unlink(missing_ok=True)




