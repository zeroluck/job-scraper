"""Stateless PostgREST-compatible clients for the scraper's data API.

JOB_DATA_API_URL accepts an API origin or its /rest/v1 endpoint. The server-only
JOB_DATA_API_TOKEN is independent of Supabase storage credentials.
"""
import os

from supabase import ClientOptions, create_client


def create_data_client(settings=None):
    """Create a client without session persistence or auth refresh requests."""
    url = os.environ.get("JOB_DATA_API_URL")
    token = os.environ.get("JOB_DATA_API_TOKEN")
    # Source credentials are storage-only. Missing target configuration must
    # stop every worker, including manual invocations outside GitHub Actions.
    if not url or not url.strip() or not token or not token.strip():
        raise ValueError("JOB_DATA_API_URL and JOB_DATA_API_TOKEN must both be set.")
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
            or parsed.path not in {"", "/", "/rest/v1", "/rest/v1/"}):
        raise ValueError("JOB_DATA_API_URL must be an HTTP(S) origin or /rest/v1 endpoint without credentials or query strings.")
    root = url.removesuffix("/").removesuffix("/rest/v1")
    return create_client(
        root, token,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )


def create_legacy_supabase_client(settings=None):
    """Keep storage rollback credentials independent of the selected data API."""
    if settings is None:
        import config as settings
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("Supabase URL and Key must be set in environment variables or config.")
    return create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )
