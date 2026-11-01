"""Exercise the workflow's actual Python probe without network or credentials."""
import json
from pathlib import Path
import ssl
import subprocess
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def python_probe():
    workflow = yaml.safe_load((ROOT / '.github/workflows/jobs_private_ca_qualification.yml').read_text())
    step = next(s for s in workflow['jobs']['tls']['steps'] if s.get('name', '').startswith('Python'))
    return step['run'].split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


@pytest.mark.parametrize('origin,authority,connect,host', [
    ('https://jobs.example', 'jobs.example', 'jobs.example:443', 'jobs.example'),
    ('https://jobs.example:8443/', 'jobs.example:8443', 'jobs.example:8443', 'jobs.example'),
    ('https://[::1]:8443', '[::1]:8443', '[::1]:8443', '::1'),
    ('https://[::1]', '[::1]', '[::1]:443', '::1'),
])
def test_python_ca_probe_preserves_https_origin_and_tls_authority(monkeypatch, origin, authority, connect, host):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv('JOB_DATA_API_URL', origin)
    monkeypatch.setenv('JOBS_TLS_QUALIFICATION_JWT', 'offline-signed-token')
    requests = []
    commands = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps([]).encode()
    def urlopen(request, *, context, timeout):
        requests.append(request.full_url)
        if len(requests) == 4:
            raise urllib.error.URLError(ssl.SSLCertVerificationError('untrusted CA'))
        if request.get_header('Authorization') != 'Bearer offline-signed-token':
            raise urllib.error.HTTPError(request.full_url, 401, 'unauthorized', {}, None)
        return Response()
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1, stderr=b'hostname mismatch')
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(subprocess, 'run', run)
    exec(compile(python_probe(), '<private-ca-workflow>', 'exec'), {})
    assert requests == [f'https://{authority}/rest/v1/jobs?select=job_id&limit=0'] * 4
    assert commands[0][commands[0].index('-connect') + 1] == connect
    assert commands[0][commands[0].index('-servername') + 1] == host


@pytest.mark.parametrize('origin', [
    'http://jobs.example', 'https://user:pass@jobs.example',
    'https://jobs.example/path', 'https://jobs.example?query=1',
    'https://jobs.example#fragment', 'https://jobs.example:bad',
    'https://jobs.example:65536', 'https://jobs.example:0',
])
def test_python_ca_probe_rejects_non_https_origins_before_requests(monkeypatch, origin):
    monkeypatch.setenv('JOB_DATA_API_URL', origin)
    monkeypatch.setenv('JOBS_TLS_QUALIFICATION_JWT', 'offline-signed-token')
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('invalid origin requested'))
    with pytest.raises((AssertionError, ValueError)):
        exec(compile(python_probe(), '<private-ca-workflow>', 'exec'), {})
