"""Build runner-local public + private CA trust without replacing public roots.

HTTPX (including Supabase/PostgREST) reads SSL_CERT_FILE. Requests instead
reads REQUESTS_CA_BUNDLE. Export both through GITHUB_ENV before worker start.
"""
import os
from pathlib import Path
import ssl

import certifi


def configure_trust(private_ca: Path, runner_temp: Path, github_env: Path) -> Path:
    private_pem = private_ca.read_bytes()
    # Validate the supplied certificate before creating/exporting a bundle.
    private_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    private_context.load_verify_locations(cadata=private_pem.decode('ascii'))
    if not private_context.get_ca_certs():
        raise ValueError('Private trust input must contain a CA certificate.')
    bundle = runner_temp.resolve() / 'job-data-api-ca-bundle.pem'
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b'\n' + private_pem + b'\n')
    ssl.create_default_context(cafile=str(bundle))
    with github_env.open('a') as output:
        output.write(f'SSL_CERT_FILE={bundle}\nREQUESTS_CA_BUNDLE={bundle}\n')
    return bundle


if __name__ == '__main__':
    configure_trust(
        Path(__file__).resolve().parents[1] / 'certs/jobs-private-root.crt',
        Path(os.environ['RUNNER_TEMP']),
        Path(os.environ['GITHUB_ENV']),
    )
