"""Offline workflow policy and real loopback TLS contracts."""
from pathlib import Path
import os
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import certifi
import httpx
import pytest
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATABASE_JOBS = {
    'analyze_jobs.yml': ['analyze'],
    'backfill_linkedin_metadata.yml': ['backfill'],
    'backfill_same_id_relists.yml': ['backfill'],
    'freehire_compat.yml': ['classify'],
    'hourly_resume_customization.yml': ['customize_resumes'],
    'job_manager.yml': ['manage'],
    'parse_resume.yml': ['parse_resume_job'],
    'score_jobs.yml': ['score'],
    'scrape_jobs.yml': ['scrape', 'freehire_compat', 'publication_gate'],
    'private_data_api_sdk.yml': ['qualify_sdk'],
}


def test_every_database_job_has_target_only_data_and_separate_source_storage():
    for filename, names in DATABASE_JOBS.items():
        workflow = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text())
        for name in names:
            job = workflow['jobs'][name]
            env = job.get('env', {})
            assert env.get('JOB_DATA_API_URL') == 'https://pgsql.jdb.l.cd', (filename, name)
            assert env.get('JOB_DATA_API_TOKEN') == '${{ secrets.JOB_DATA_API_TOKEN }}'
            assert env.get('JOB_STORAGE_BACKEND') == 'supabase'
            setup = [i for i, step in enumerate(job['steps']) if step.get('uses') == './.github/actions/configure-data-api']
            assert len(setup) == 1
            for i, step in enumerate(job['steps']):
                if 'SUPABASE_URL' in step.get('env', {}):
                    assert setup[0] < i
                    assert step['env']['SUPABASE_URL'] == '${{ secrets.SUPABASE_URL }}'
                    assert step['env']['SUPABASE_SERVICE_ROLE_KEY'] == '${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}'
                    assert 'JOB_DATA_API_URL' not in step['env']


def test_qualification_workflow_is_manual_read_only_and_has_no_storage_credentials():
    workflow = yaml.safe_load((ROOT / '.github/workflows/private_data_api_sdk.yml').read_text())
    assert workflow[True] == {'workflow_dispatch': None}
    assert workflow['permissions'] == {'contents': 'read'}
    assert list(workflow['jobs']) == ['qualify_sdk']
    job = workflow['jobs']['qualify_sdk']
    assert job['timeout-minutes'] == 5
    assert not any(name.startswith('SUPABASE_') for name in job['env'])
    assert job['steps'][-1]['run'] == 'python -m scripts.qualify_data_api'
    assert 'scraper.py' not in str(job)


def test_production_ca_is_a_public_ca_certificate():
    pem = (ROOT / 'certs/jobs-private-root.crt').read_text()
    assert 'PRIVATE KEY' not in pem
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=pem)
    assert len(context.get_ca_certs()) == 1


def test_bundle_preserves_public_roots_and_exports_both_http_stacks(tmp_path):
    from scripts.configure_data_api import configure_trust

    output = tmp_path / 'github-env'
    bundle = configure_trust(ROOT / 'certs/jobs-private-root.crt', tmp_path, output)
    assert Path(bundle).read_bytes().startswith(Path(certifi.where()).read_bytes())
    context = ssl.create_default_context(cafile=str(bundle))
    assert len(context.get_ca_certs()) >= len(ssl.create_default_context(cafile=certifi.where()).get_ca_certs())
    assert output.read_text() == f'SSL_CERT_FILE={bundle}\nREQUESTS_CA_BUNDLE={bundle}\n'


def test_invalid_ca_does_not_export_trust(tmp_path):
    from scripts.configure_data_api import configure_trust

    ca = tmp_path / 'invalid.crt'
    ca.write_text('not a certificate')
    output = tmp_path / 'github-env'
    with pytest.raises(ssl.SSLError):
        configure_trust(ca, tmp_path, output)
    assert not output.exists()


def test_combined_bundle_is_actually_used_by_httpx_requests_and_supabase(tmp_path, monkeypatch):
    from scripts.configure_data_api import configure_trust
    from data_client import create_data_client

    # Ephemeral test-only CA/key, never the production CA's private key.
    for args in [
        ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.crt', '-days', '1', '-subj', '/CN=Offline test CA', '-addext', 'basicConstraints=critical,CA:TRUE'],
        ['req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=localhost'],
    ]:
        subprocess.run(['openssl', *args], cwd=tmp_path, check=True, capture_output=True)
    extensions = tmp_path / 'server.ext'
    extensions.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nauthorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\nsubjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n')
    subprocess.run(['openssl', 'x509', '-req', '-in', 'server.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-CAcreateserial', '-out', 'server.crt', '-days', '1', '-extfile', str(extensions)], cwd=tmp_path, check=True, capture_output=True)
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization')))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"version":1}' if '/rpc/' in self.path else b'[{"job_id":"offline"}]')

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path / 'server.crt', tmp_path / 'server.key')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'https://localhost:{server.server_port}'
    monkeypatch.setenv('NO_PROXY', 'localhost,127.0.0.1')
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('REQUESTS_CA_BUNDLE', raising=False)
    try:
        with pytest.raises(httpx.ConnectError):
            httpx.get(url, timeout=3)
        with pytest.raises(requests.exceptions.SSLError):
            requests.get(url, timeout=3)
        output = tmp_path / 'github-env'
        configure_trust(tmp_path / 'ca.crt', tmp_path, output)
        for line in output.read_text().splitlines():
            key, value = line.split('=', 1)
            monkeypatch.setenv(key, value)
        assert httpx.get(url, timeout=3).status_code == 200
        assert requests.get(url, timeout=3).status_code == 200
        monkeypatch.setenv('JOB_DATA_API_URL', url)
        monkeypatch.setenv('JOB_DATA_API_TOKEN', 'offline-target-jwt')
        client = create_data_client()
        assert client.table('jobs').select('job_id').execute().data == [{'job_id': 'offline'}]
        assert seen[-1] == ('/rest/v1/jobs?select=job_id', 'Bearer offline-target-jwt')
        from scripts.qualify_data_api import qualify
        assert qualify()['sdk_read_only_rpc'] == 'passed'
        assert seen[-1] == ('/rest/v1/rpc/get_scraper_configuration', 'Bearer offline-target-jwt')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
