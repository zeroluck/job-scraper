# Private data API runner support

## Runtime contract

- Data clients require both `JOB_DATA_API_URL` and `JOB_DATA_API_TOKEN`. Missing,
  empty or whitespace-only values stop the worker. There is no automatic source
  database fallback, including for workers started outside Actions.
- All production database jobs select `https://pgsql.jdb.l.cd` and
  `${{ secrets.JOB_DATA_API_TOKEN }}`. No JWT role/header override or database
  grants are introduced. Existing table/RPC names and named arguments remain.
- `JOB_STORAGE_BACKEND=supabase` preserves object storage on the original
  `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`. A separate source SDK client is
  always built for storage; the target data client is never reused for storage.
  The copied adapter also retains its opt-in S3 implementation, but production
  workflows reject non-Supabase storage. `boto3` is its explicit dependency.
- The composite action runs after dependency installation and before any database
  consumer, including the optional source-circuit reset. It concatenates installed
  certifi public roots and `certs/jobs-private-root.crt` into `RUNNER_TEMP`, then
  exports **both** `SSL_CERT_FILE` (HTTPX/Supabase/PostgREST) and
  `REQUESTS_CA_BUNDLE` (Requests) through `GITHUB_ENV`. It never alters certifi's
  installed bundle, changes the system trust store or disables verification.
- The certificate is public CA material copied from the provided recovery root.
  SHA-256 fingerprint:
  `C3:B3:CA:EE:73:A9:A0:01:87:59:88:4B:04:A4:F9:47:77:09:BE:FB:0D:2E:B7:24:CF:8B:20:B0:9C:A2:B9:DA`.

## Isolated qualification

`.github/workflows/private_data_api_sdk.yml` has only `workflow_dispatch`, a
five-minute timeout and `contents: read`. It receives no source/storage secrets,
imports no workers, and runs `python -m scripts.qualify_data_api` after configuring
trust. The same module can be run by the existing private-CA temporary-branch
harness; a newly added workflow may need default-branch registration before the
GitHub dispatch UI exposes it.

The module uses `create_data_client` for a signed `GET /rest/v1/jobs` selecting
only `job_id` with limit 1, followed by
`GET /rest/v1/rpc/get_scraper_configuration` (`get=True` forces PostgREST read-only
transaction mode). Both requests additionally send `Prefer: tx=rollback`.
Only pass/fail and installed dependency versions are printed. Configuration,
rows, tokens and raw exception/server payloads are not printed. No claim,
publication, scoring, storage or mutation operation is performed.

This does not enable target writes or supersede the parent's fencing, rollback,
authorization and live-runner gates. Do not run production workers merely to
qualify TLS. No remote workflow was dispatched by this implementation task.

## Local verification

Base: remote `main` at `97641d7e8c41f4ed5dd255452a80213a84a94ff5`, isolated
worktree `/Users/tmaerz/projects/job-scraper-cutover337`.

Python 3.11.16, installed via uv with actual dependencies:
`supabase==2.33.0`, `httpx==0.28.1`, `requests==2.34.2`,
`certifi==2026.10.23`, `pytest==9.2.0`, `pytest-socket==0.8.1`.
Production dependencies remain unpinned; runner qualification prints actual
resolved SDK versions to make drift visible.

```bash
PYTHON_DOTENV_DISABLED=1 LITELLM_LOCAL_MODEL_COST_MAP=True \
JOB_DATA_API_URL=https://data.example.test JOB_DATA_API_TOKEN=offline-target \
SUPABASE_URL=https://source.example.test SUPABASE_SERVICE_ROLE_KEY=offline-source \
.venv/bin/python -m pytest \
  tests/test_data_client.py tests/test_storage_adapter.py \
  tests/test_private_ca_workflows.py tests/test_qualify_data_api.py \
  --disable-socket --allow-hosts=127.0.0.1,::1 \
  --basetemp /Users/tmaerz/.hermes/cache/scratch/cutover337-retest -q
```

- Focused: **47 passed**, 14 SDK deprecation warnings.
- Full suite: **512 passed, 7 failed**, 16 SDK deprecation warnings.
- Unmodified `git archive HEAD` baseline, same interpreter/environment/network
  restrictions: **465 passed, the same 7 failed**, 2 SDK warnings. No new failing
  test IDs. Existing failures concern job-manager `response_text_lower`, incomplete
  scraper mocks and two stale workflow assertions omitting `gate_watchdog`.
- Real ephemeral loopback TLS: HTTPX and Requests reject the private server before
  trust is exported; HTTPX, Requests, actual Supabase/PostgREST and the qualification
  module succeed after the combined bundle is exported. Public roots remain in
  the bundle. External socket connections are blocked during these tests.
- `actionlint==1.7.12` (release checksum verified), with unavailable shellcheck/
  pyflakes integrations disabled: passed. Updated the pre-existing obsolete
  `parse_resume.yml` setup-python v4 reference to v5 to satisfy this check.
- `git diff --check`: passed. New-file security scan found no private keys,
  `verify=False`, unsafe shell execution, eval or pickle deserialization.

These are offline/local transport and policy results, **not** a claim of live
SDK authorization or a completed production cutover. Parent review and isolated
live runner execution remain outstanding. No commits, pushes, remote writes,
secret changes, source data changes or service changes were performed.
