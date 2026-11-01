"""Real SDK transport contracts for the read-only runner qualification."""
import httpx
import pytest


def test_qualification_only_uses_signed_read_only_requests(monkeypatch, capsys):
    from scripts.qualify_data_api import qualify

    monkeypatch.setenv('JOB_DATA_API_URL', 'https://pgsql.jdb.l.cd')
    monkeypatch.setenv('JOB_DATA_API_TOKEN', 'offline-signed-jwt')
    requests = []

    def send(self, request, **kwargs):
        requests.append(request)
        assert request.method == 'GET'
        assert request.headers['Authorization'] == 'Bearer offline-signed-jwt'
        assert request.headers['Prefer'] == 'tx=rollback'
        data = {'private_config_marker': True} if '/rpc/' in request.url.path else [{'job_id': 'private_row_marker'}]
        return httpx.Response(200, json=data, request=request)

    monkeypatch.setattr(httpx.Client, 'send', send)
    result = qualify()
    assert [(r.method, r.url.path) for r in requests] == [('GET', '/rest/v1/jobs'), ('GET', '/rest/v1/rpc/get_scraper_configuration')]
    assert requests[0].url.params['select'] == 'job_id'
    assert requests[0].url.params['limit'] == '1'
    assert result['sdk_get'] == 'passed'
    assert result['sdk_read_only_rpc'] == 'passed'
    assert result['versions']['httpx']
    assert capsys.readouterr().out == ''
    assert 'private_' not in str(result)


def test_qualification_failure_does_not_print_server_payload_or_credentials(monkeypatch, capsys):
    from scripts import qualify_data_api

    def fail():
        raise RuntimeError('secret-payload-and-token')

    monkeypatch.setattr(qualify_data_api, 'qualify', fail)
    assert qualify_data_api.main() == 1
    output = capsys.readouterr()
    assert 'secret-payload-and-token' not in output.out + output.err
    assert 'RuntimeError' in output.err
