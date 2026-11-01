"""Read-only SDK qualification. Run: python -m scripts.qualify_data_api.

Uses only the explicit data API token. GET RPC forces a read-only PostgREST
transaction; Prefer: tx=rollback additionally requests rollback. Never import
workers or print row/configuration payloads, credentials, or raw exceptions.
"""
from importlib.metadata import version
import json
import sys

from data_client import create_data_client


def qualify() -> dict:
    client = create_data_client()
    # Pass through SDK options before the PostgREST transport is constructed.
    client.options.headers['Prefer'] = 'tx=rollback'
    rows = client.table('jobs').select('job_id').limit(1).execute()
    if not isinstance(rows.data, list):
        raise RuntimeError('Unexpected GET response shape.')
    configuration = client.rpc('get_scraper_configuration', get=True).execute()
    if configuration.data in (None, [], {}):
        raise RuntimeError('Configuration RPC returned no configuration.')
    return {
        'sdk_get': 'passed',
        'sdk_read_only_rpc': 'passed',
        'versions': {name: version(name) for name in ('supabase', 'httpx', 'certifi')},
    }


def main() -> int:
    try:
        result = qualify()
    except Exception as exc:
        print(f'SDK qualification failed ({type(exc).__name__}); payload suppressed.', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
