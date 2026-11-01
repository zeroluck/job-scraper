"""Offline client configuration contracts; no auth or network requests."""
from types import SimpleNamespace

from pathlib import Path

import pytest


@pytest.mark.parametrize("module_name", ["analyze_jobs", "backfill_membership_filters", "publication_gate", "backfill_freehire_compat"])
def test_entrypoint_factories_use_shared_configuration(monkeypatch, module_name):
    import importlib
    import data_client

    expected = object()
    monkeypatch.setattr(data_client, "create_data_client", lambda *args: expected)
    module = importlib.import_module(module_name)
    assert module._get_db() is expected


def test_shared_supabase_client_uses_factory():
    import ast

    root = Path(__file__).resolve().parents[1]
    source = (root / "supabase_utils.py").read_text()
    tree = ast.parse(source)
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "supabase"]
    assert isinstance(assignments[0].value, ast.Call)
    assert assignments[0].value.func.id == "create_data_client"
    assert "if not config.SUPABASE_URL" not in (root / "score_jobs.py").read_text()


@pytest.mark.parametrize("url", ["https://data.example.test/rest/v2", "https://data.example.test?token=private", "https://data.example.test/#fragment", "https://user:secret@data.example.test", "ftp://data.example.test"])
def test_invalid_explicit_endpoint_fails_closed_without_echoing_url(monkeypatch, url):
    import data_client

    monkeypatch.setenv("JOB_DATA_API_URL", url)
    monkeypatch.setenv("JOB_DATA_API_TOKEN", "private-token")
    with pytest.raises(ValueError, match="JOB_DATA_API_URL") as error:
        data_client.create_data_client()
    assert url not in str(error.value)
    assert "private-token" not in str(error.value)


@pytest.mark.parametrize("url", ["https://data.example.test", "https://data.example.test/", "https://data.example.test/rest/v1", "https://data.example.test/rest/v1/"])
def test_rest_wire_contract_keeps_named_rpc_and_embedding(monkeypatch, url):
    import json
    import httpx
    import data_client

    monkeypatch.setenv("JOB_DATA_API_URL", url)
    monkeypatch.setenv("JOB_DATA_API_TOKEN", "runner-jwt")
    requests = []

    def send(self, request, **kwargs):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer runner-jwt"
        if request.method == "POST":
            return httpx.Response(200, json=True, request=request)
        return httpx.Response(200, json=[{"job_id": "job-1"}], headers={"Content-Range": "0-0/1"}, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    client = data_client.create_data_client()
    assert client.rpc("replace_base_resume", {"p_resume_data": {"name": "Offline"}}).execute().data is True
    assert requests[0].url.path == "/rest/v1/rpc/replace_base_resume"
    assert json.loads(requests[0].content) == {"p_resume_data": {"name": "Offline"}}
    result = client.table("jobs").select("job_id,customized_resumes!jobs_customized_resume_id_fkey(*)", count="exact").range(0, 0).execute()
    assert result.data == [{"job_id": "job-1"}]
    assert result.count == 1
    assert requests[1].url.path == "/rest/v1/jobs"
    assert "jobs_customized_resume_id_fkey" in requests[1].url.params["select"]


@pytest.fixture(autouse=True)
def clean_data_environment(monkeypatch):
    monkeypatch.delenv("JOB_DATA_API_URL", raising=False)
    monkeypatch.delenv("JOB_DATA_API_TOKEN", raising=False)


def test_missing_target_configuration_never_falls_back_to_source():
    import data_client

    settings = SimpleNamespace(SUPABASE_URL="https://old.example.test", SUPABASE_SERVICE_ROLE_KEY="old-key")
    with pytest.raises(ValueError, match="JOB_DATA_API_URL and JOB_DATA_API_TOKEN"):
        data_client.create_data_client(settings)


@pytest.mark.parametrize("url,token", [("https://data.example.test", None), (None, "jwt"), ("", "jwt"), ("https://data.example.test", "")])
def test_incomplete_explicit_configuration_never_mixes_credentials(monkeypatch, url, token):
    import data_client

    if url is not None:
        monkeypatch.setenv("JOB_DATA_API_URL", url)
    if token is not None:
        monkeypatch.setenv("JOB_DATA_API_TOKEN", token)
    settings = SimpleNamespace(SUPABASE_URL="https://old.example.test", SUPABASE_SERVICE_ROLE_KEY="old-key")
    with pytest.raises(ValueError, match="JOB_DATA_API_URL and JOB_DATA_API_TOKEN"):
        data_client.create_data_client(settings)


def test_explicit_data_endpoint_and_token_override_supabase(monkeypatch):
    import data_client

    monkeypatch.setenv("JOB_DATA_API_URL", "https://data.example.test/rest/v1")
    monkeypatch.setenv("JOB_DATA_API_TOKEN", "runner-jwt")
    settings = SimpleNamespace(SUPABASE_URL="https://old.example.test", SUPABASE_SERVICE_ROLE_KEY="old-key")
    client = data_client.create_data_client(settings)
    assert str(client.rest_url).rstrip("/") == "https://data.example.test/rest/v1"
    assert client.options.headers["Authorization"] == "Bearer runner-jwt"
    assert client.options.persist_session is False
    assert client.options.auto_refresh_token is False
