"""Independently switchable resume object storage; Supabase is the default.

JOB_STORAGE_BACKEND=s3 requires JOB_S3_ENDPOINT, JOB_S3_REGION,
JOB_S3_ACCESS_KEY_ID and JOB_S3_SECRET_ACCESS_KEY. S3 uses SigV4/path-style
addressing and private object keys unchanged. No bucket provisioning, public
ACLs, or credential discovery is performed. Supabase rollback continues to use
SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY, independent of JOB_DATA_API_URL/TOKEN.
"""


class SupabaseStorage:
    def __init__(self, client):
        self.client = client

    def upload_pdf(self, bucket: str, key: str, content: bytes) -> str:
        self.client.storage.from_(bucket).upload(
            path=key, file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        return key

    def download(self, bucket: str, key: str) -> bytes:
        return self.client.storage.from_(bucket).download(key)


class S3Storage:
    def __init__(self, client):
        self.client = client

    def upload_pdf(self, bucket: str, key: str, content: bytes) -> str:
        self.client.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/pdf")
        return key

    def download(self, bucket: str, key: str) -> bytes:
        body = self.client.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            return body.read()
        finally:
            body.close()


def get_storage_adapter(*, supabase_client=None):
    import os

    backend = os.environ.get("JOB_STORAGE_BACKEND", "supabase")
    if backend not in {"supabase", "s3"}:
        raise ValueError("JOB_STORAGE_BACKEND must be supabase or s3.")
    if backend == "s3":
        required = ("JOB_S3_ENDPOINT", "JOB_S3_REGION", "JOB_S3_ACCESS_KEY_ID", "JOB_S3_SECRET_ACCESS_KEY")
        if any(not os.environ.get(name) for name in required):
            raise ValueError("S3 configuration requires " + ", ".join(required))
        from urllib.parse import urlsplit

        endpoint = urlsplit(os.environ["JOB_S3_ENDPOINT"])
        if (endpoint.scheme not in {"http", "https"} or not endpoint.hostname
                or endpoint.username is not None or endpoint.password is not None
                or endpoint.query or endpoint.fragment):
            raise ValueError("JOB_S3_ENDPOINT must be an HTTP(S) endpoint without credentials or query strings.")
        import boto3
        from botocore.config import Config

        return S3Storage(boto3.client(
            "s3", endpoint_url=os.environ["JOB_S3_ENDPOINT"],
            region_name=os.environ["JOB_S3_REGION"],
            aws_access_key_id=os.environ["JOB_S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["JOB_S3_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        ))
    # Data clients are target-only; never reuse one for source object storage,
    # even if its original environment has since been removed.
    from data_client import create_legacy_supabase_client

    return SupabaseStorage(create_legacy_supabase_client())
