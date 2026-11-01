"""Offline object storage contracts for existing resume operations."""
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("endpoint", ["https://user:private@files.example.test", "https://files.example.test?secret=private", "https://files.example.test/#fragment", "ftp://files.example.test"])
def test_s3_endpoint_rejects_embedded_secrets(monkeypatch, endpoint):
    import storage_adapter

    monkeypatch.setenv("JOB_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("JOB_S3_ENDPOINT", endpoint)
    for name in ["JOB_S3_REGION", "JOB_S3_ACCESS_KEY_ID", "JOB_S3_SECRET_ACCESS_KEY"]:
        monkeypatch.setenv(name, "offline")
    with pytest.raises(ValueError, match="JOB_S3_ENDPOINT") as error:
        storage_adapter.get_storage_adapter()
    assert endpoint not in str(error.value)


@pytest.mark.parametrize("failure", [None, RuntimeError("offline storage failure")])
def test_existing_resume_operations_route_through_adapter(monkeypatch, failure):
    import supabase_utils
    import storage_adapter

    calls = []
    class Adapter:
        def upload_pdf(self, bucket, key, content):
            calls.append(("upload", bucket, key, content))
            if failure:
                raise failure
            return key
        def download(self, bucket, key):
            calls.append(("download", bucket, key))
            if failure:
                raise failure
            return b"pdf"
    monkeypatch.setattr(storage_adapter, "get_storage_adapter", lambda **kwargs: Adapter())
    key = "technology_delivery/job-1/version.pdf"
    assert supabase_utils.upload_customized_resume_to_storage(b"pdf", key) == (None if failure else key)
    assert supabase_utils.download_resume_from_storage() == (None if failure else b"pdf")
    assert calls == [("upload", "personalized_resumes", key, b"pdf"), ("download", "resumes", "resume.pdf")]


def test_supabase_storage_does_not_follow_data_api_override(monkeypatch):
    import config
    import storage_adapter

    monkeypatch.setenv("JOB_STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("JOB_DATA_API_URL", "https://data.example.test")
    monkeypatch.setenv("JOB_DATA_API_TOKEN", "runner-jwt")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://old.example.test")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_ROLE_KEY", "old-key")
    adapter = storage_adapter.get_storage_adapter(supabase_client=object())
    assert str(adapter.client.storage_url).startswith("https://old.example.test/storage/v1")
    assert adapter.client.options.headers["Authorization"] == "Bearer old-key"


@pytest.mark.parametrize("backend", ["supabase", "s3"])
def test_download_returns_bytes_and_closes_s3_body(backend):
    import io
    import boto3
    import storage_adapter
    from botocore.stub import Stubber

    if backend == "supabase":
        class Storage:
            def from_(self, bucket):
                assert bucket == "resumes"
                return SimpleNamespace(download=lambda key: b"pdf" if key == "résumé.pdf" else None)
        adapter = storage_adapter.SupabaseStorage(SimpleNamespace(storage=Storage()))
        assert adapter.download("resumes", "résumé.pdf") == b"pdf"
    else:
        client = boto3.client("s3", endpoint_url="https://files.example.test", region_name="garage", aws_access_key_id="offline", aws_secret_access_key="offline")
        adapter = storage_adapter.S3Storage(client)
        body = io.BytesIO(b"pdf")
        with Stubber(client) as stub:
            stub.add_response("get_object", {"Body": body}, {"Bucket": "resumes", "Key": "résumé.pdf"})
            assert adapter.download("resumes", "résumé.pdf") == b"pdf"
            assert body.closed
            stub.assert_no_pending_responses()


@pytest.mark.parametrize("backend", ["s33", "", "SUPABASE"])
def test_unknown_backend_fails_closed(monkeypatch, backend):
    import storage_adapter

    monkeypatch.setenv("JOB_STORAGE_BACKEND", backend)
    with pytest.raises(ValueError, match="JOB_STORAGE_BACKEND"):
        storage_adapter.get_storage_adapter()


@pytest.mark.parametrize("missing", ["JOB_S3_ENDPOINT", "JOB_S3_REGION", "JOB_S3_ACCESS_KEY_ID", "JOB_S3_SECRET_ACCESS_KEY"])
def test_partial_s3_configuration_fails_before_credentials_discovery(monkeypatch, missing):
    import storage_adapter

    monkeypatch.setenv("JOB_STORAGE_BACKEND", "s3")
    for name in ["JOB_S3_ENDPOINT", "JOB_S3_REGION", "JOB_S3_ACCESS_KEY_ID", "JOB_S3_SECRET_ACCESS_KEY"]:
        monkeypatch.setenv(name, "https://files.example.test" if name == "JOB_S3_ENDPOINT" else "offline")
    monkeypatch.setenv(missing, "")
    with pytest.raises(ValueError, match="S3 configuration"):
        storage_adapter.get_storage_adapter()


def test_s3_upload_uses_path_style_sigv4_without_supabase(monkeypatch):
    import boto3
    import storage_adapter
    from botocore.stub import Stubber

    monkeypatch.setenv("JOB_STORAGE_BACKEND", "s3")
    for name, value in {
        "JOB_S3_ENDPOINT": "https://files.example.test",
        "JOB_S3_REGION": "garage",
        "JOB_S3_ACCESS_KEY_ID": "offline-id",
        "JOB_S3_SECRET_ACCESS_KEY": "offline-secret",
    }.items():
        monkeypatch.setenv(name, value)
    real_client = boto3.client
    captured = {}

    def capture(service, **kwargs):
        captured.update(kwargs)
        return real_client(service, **kwargs)

    monkeypatch.setattr(boto3, "client", capture)
    adapter = storage_adapter.get_storage_adapter()
    assert captured["endpoint_url"] == "https://files.example.test"
    assert captured["region_name"] == "garage"
    assert captured["config"].s3["addressing_style"] == "path"
    assert captured["config"].signature_version == "s3v4"
    key = "network_infrastructure/job-1/résumé #1.pdf"
    with Stubber(adapter.client) as stub:
        stub.add_response("put_object", {}, {"Bucket": "personalized_resumes", "Key": key, "Body": b"pdf", "ContentType": "application/pdf"})
        assert adapter.upload_pdf("personalized_resumes", key, b"pdf") == key
        stub.assert_no_pending_responses()


def test_supabase_storage_ignores_target_client_even_if_environment_is_removed(monkeypatch):
    import data_client
    import storage_adapter

    monkeypatch.setenv('JOB_STORAGE_BACKEND', 'supabase')
    monkeypatch.delenv('JOB_DATA_API_URL', raising=False)
    monkeypatch.delenv('JOB_DATA_API_TOKEN', raising=False)
    source = object()
    monkeypatch.setattr(data_client, 'create_legacy_supabase_client', lambda: source)
    assert storage_adapter.get_storage_adapter(supabase_client=object()).client is source


def test_default_supabase_storage_preserves_upload_signature(monkeypatch):
    import storage_adapter

    monkeypatch.delenv("JOB_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("JOB_DATA_API_URL", raising=False)
    monkeypatch.delenv("JOB_DATA_API_TOKEN", raising=False)
    calls = []

    class Bucket:
        def upload(self, **kwargs):
            calls.append(kwargs)

    class Storage:
        def from_(self, bucket):
            assert bucket == "personalized_resumes"
            return Bucket()

    import data_client
    monkeypatch.setattr(data_client, 'create_legacy_supabase_client', lambda: SimpleNamespace(storage=Storage()))
    adapter = storage_adapter.get_storage_adapter()
    key = "technology_delivery/job-1/résumé #1.pdf"
    assert adapter.upload_pdf("personalized_resumes", key, b"pdf") == key
    assert calls == [{"path": key, "file": b"pdf", "file_options": {"content-type": "application/pdf", "upsert": "true"}}]
