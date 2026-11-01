# Workflow qualification handoff

## Outcome and gates

GitHub currently reports **12**, not 13, registered workflows: 3 active plus 9
`disabled_manually`. There are 11 files on main plus one historical branch-only
private-CA workflow. `workflow-qualification-matrix.json` contains exactly one
item per observed workflow, original dispatch inputs, bounded future commands,
limits, expected persistent outcomes, current states and blockers.

No workflow was enabled or dispatched; no source was pushed and no database or
Storage service was mutated. The target promotion and initial native FreeHire
pull remain parent-owned gates. Do not run writer commands until those gates
and explicit writer authorization are satisfied.

Eight existing writer workflows now have opt-in `qualification=false` and
`qualification_archetype` inputs. With qualification true the fresh process runs
the actual intended worker (not a stub), caps processing to one candidate/lane
(scoring has one initial plus one custom rescore candidate), and shares a hard
two-provider-invocation budget. Failed provider calls count. Each call has a
4096-output-token, 50000-serialized-message-character and 30-second timeout cap;
LiteLLM retries are disabled. A 300-second process deadline exits even through
ordinary worker Exception handlers. Interrupted claims require inspection before
retry. This is not an exact dollar-cost guarantee. Native
worker failures may be swallowed by their existing code; **execution_returned
is not a pass**. Independent persistent readback is mandatory.

Resume customization necessarily uploads at most one intended PDF; this tests
its actual storage behavior. Parse-resume only downloads its existing lane PDF.
No notification integration is invoked by the eight prepared paths. Scraper
`suppress_notifications=true` suppresses only the issue watchdog, preserving the
actual compatibility/publication job conditions. It is NOT bounded qualification.

## Not safe to dispatch yet

- `job_manager.yml`: bounded mode invokes real expiry and activity operations,
  each selecting one distinct explicit canonical ID (`qualification_expiry_job_id`
  and `qualification_activity_job_id`). Both selection and updates protect active
  and applied/offer/interviewing rows. API/check failures propagate; deletion is
  not invoked. The undefined response variable and mixed-case inactive keyword
  matching are fixed. Independently verify the selected IDs' lane membership and
  eligibility before authorization; a lane argument is not a row-membership proof.
- `scrape_jobs.yml`: partial discovery primitives now bound one execution/scope,
  one search attempt, at most one card, one detail task and one detail attempt.
  Oversized pages fail rather than fabricating coverage by truncation; shared
  resumes are rejected. These primitives are NOT wired to a dispatchable scraper
  qualification mode. Task claims are global (the RPC has no cycle/lane filter),
  and the full publication finalizer can affect global pending work. A safe real
  scoped-claim/publication envelope remains unresolved. Never bypass coverage,
  replace the worker with mocks, or claim single-lane recovery qualifies publication.
- `jobs_private_ca_qualification.yml`: historical source from the existing successful
  run was restored locally, manual-only, with repository-variable endpoint config
  and the tracked public CA. Curl, Python and Node signed reads plus auth/TLS
  negative checks are preserved. No new remote run occurred; source remains absent
  on main until reviewed publication. The separate qualification JWT remains a secret.
- All eight prepared writer paths require review/publication and parent authorization.
  Empty eligibility or zero changed rows is not persistent writer qualification.

## Reproduce local checks (no live credentials)

Run with a Python environment installed from `requirements.txt` plus `pytest`
and `PyYAML`. In this checkout the available interpreter is
`../job-scraper-cutover337/.venv/bin/python`. Remove inherited `PYTHONPATH` to
avoid loading Hermes Python 3.14 packages into project Python 3.11:

```sh
env -u PYTHONPATH PYTHON_DOTENV_DISABLED=1 \
  JOB_DATA_API_URL=https://api.example.test JOB_DATA_API_TOKEN=offline-token \
  SUPABASE_URL=https://storage.example.test SUPABASE_SERVICE_ROLE_KEY=offline-storage-token \
  ../job-scraper-cutover337/.venv/bin/python -m pytest \
  tests/test_workflow_qualification.py tests/test_workflow_qualification_more.py \
  tests/test_analyze_jobs.py tests/test_backfill_freehire_compat.py \
  tests/test_backfill_linkedin_metadata.py tests/test_backfill_same_id_relists.py \
  tests/test_resume_parser.py tests/test_score_jobs.py tests/test_private_ca_workflows.py -q
```

Verified on the parent commit: **524 passed, 7 failed**. Latest shared-worktree
suite (including concurrent job-manager/CA fixes): **591 passed, 6 failed**, with
16 existing SDK deprecation warnings. This envelope change's focused suite is
**32 passed**, including nine new envelope regressions/integration cases. The exact
activity-grant NameError regression is fixed; the other six failures are unchanged:
four incomplete offline database mocks and two stale workflow expectations omitting
`gate_watchdog`. No baseline failure was hidden or weakened. Focused tests and
restored CA shell syntax checks pass; `git diff --check` passes. All verification
uses inert `.test` authority configuration, not production credentials.

## Shared persistent envelope and minimal scraper contract

A metadata candidate limit is **not** a request or database-row limit. Actual
`execute('backfill_linkedin_metadata', lane)` reaches the real worker, parser,
`DurableLinkedInRequestGate` and SDK RPC helpers. With `MAX_RETRIES=3`, one
candidate can issue four HTTP requests and four grants; first-404 confirmation
uses two. Failed requests finish with `http_error`, `transport_error`, or
`terminal_unavailable`; successful metadata requires `complete` plus job readback.
Unavailable pages may still persist `detail_metadata_checked_at`, which is not
successful metadata recovery. Grant acquisition can expire unrelated pending
grants even when it returns wait/circuit-open. Creation/consumption advances the
shared policy timing. A challenge opens the shared circuit, increments its
generation, invalidates other producers' pending/consumed grants, and updates
unfinished `linkedin_discovery_task_attempts`. Never automatically reset/retry.

The matrix now requires unfiltered before/after snapshots of these three gate
tables for metadata, job-manager and scraper, plus all directly affected tables.
`jobs` mutations also trigger `canonical_provider_revisions` updates. Full
snapshots establish absence of collateral changes; candidate-only hashes do not.
Fence other writers for attribution and inspect exact grant IDs, classes, status,
timestamps, policy generation/reason/timing and outside-candidate changes.
`qualification_archetype` validates configuration but does **not** lane-filter
FreeHire compatibility, metadata or same-ID backfill: each selects one **global**
canonical candidate. Authorize that identity, not an assumed lane boundary.

True bounded production scraper qualification remains blocked, not passed:

1. `claim_linkedin_discovery_tasks(p_worker_id,p_limit,p_order_mode)` has neither
   cycle nor ingestion-run scope. Before claiming it globally reclaims **all**
   expired leases, including terminalizing exhausted ones. Filtering returned tasks
   in Python cannot undo those writes. A parent-reviewed scoped contract must
   validate cycle/run/lane ownership and constrain both lease reclamation and
   selection before writes, retaining owner/lease-token checks and receipts.
2. Discovery qualification cannot silently drop cards or declare exhaustion after
   a nonempty first page. Define a bounded query scope, retain every returned card,
   and allow enough real pagination to prove exhaustion within the cap; if the cap
   is reached, persist incomplete/failed evidence and reject publication. Single
   page primitives are not full scraper acceptance.
3. Compatibility must select the resulting explicit canonical IDs, not unrelated
   global pending jobs. `finalize_freehire_publication_v2` checks predecessors and
   debt globally, marks all sealed predecessor cycles applied, calls the global
   snapshot finalizer, and advances singleton publication state/generation. A
   cycle argument does not isolate publication. Do not add a bypass or call this
   against production pending work under a one-row claim.
4. The narrow safe rehearsal without changing production RPCs is a separate,
   identity-guarded database/API and Storage namespace, with source credentials
   unavailable, no other writers/pending tasks, and unchanged actual pipeline
   entrypoints. Exercise discovery, detail/canonical apply, compatibility and
   genuine snapshot finalization there, with issue watchdog/notifications and
   downstream FreeHire pull disabled. Read back every matrix table and exact
   publication artifact. This qualifies the isolated authority only. To run on a
   shared production authority instead requires parent-reviewed scoped claims,
   explicit-ID compatibility and an isolated publication namespace (including
   watermarks/generation/snapshots), or explicit authorization of the full global
   publication envelope. None of those DB changes or authorizations is implied.

Offline regression tests exercise the actual qualification metadata path with
HTTP/RPC boundary doubles for success, retry amplification, two-404 terminal
unavailability, challenge invalidation and exhausted HTTP failures. Real
`LLMClient` instances exercise shared failure/fallback budget through the runner's
provider wrapper; no network provider is called. Failure receipts include error
type, attempted-call count and mandatory readback without echoing exception
messages; a receipt does not prove persistent success. Worker-internal logs retain
their existing behavior. No live PostgreSQL/pipeline qualification occurred.

## Independent GitHub read-only checks

```sh
gh api 'repos/zeroluck/job-scraper/actions/workflows?per_page=100' \
  --jq '{total_count,workflows:[.workflows[]|{id,name,path,state}]}'
gh api repos/zeroluck/job-scraper/commits/main --jq .sha
gh api 'repos/zeroluck/job-scraper/actions/workflows/403167574/runs?per_page=1' \
  --jq '.workflow_runs[]|{id,head_sha,status,conclusion,event}'
```

Use the JSON per-item commands only after the specified gates. For readback,
record protected before/after snapshots under the parent's operations directory,
including changed job IDs, lane IDs, claim owners/expiry, table counts/hashes,
object hashes where applicable, and target identity. Do not publish private
resume payloads, tokens, endpoint values or operational snapshots into Git.
