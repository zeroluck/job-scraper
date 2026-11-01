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

Seven existing writer workflows now have opt-in `qualification=false` and
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
No notification integration is invoked by the seven prepared paths. The scraper
watchdog is NOT qualified or suppressed by this patch: scraper remains blocked.

## Not safe to dispatch yet

- `job_manager.yml`: no inputs; bulk expiry is not capped, and existing tests
  prove activity checks reference undefined `response_text_lower`. Needs scoped
  expiry/activity selection and failure propagation before write qualification.
- `scrape_jobs.yml`: selecting one archetype does not cap adaptive discovery
  tasks/results and skips compatibility/publication/watchdog. Full pipeline can
  write GitHub issues. Needs a real task/row bound, watchdog suppression, and
  publication acceptance after the initial native pull.
- `jobs_private_ca_qualification.yml`: active historical registration but absent
  on main. Historical branch source only triggers on push, has no dispatch, uses
  a separate qualification JWT, and passed run `41256576568`. Do not fabricate a
  dispatch command; restore reviewed manual-only source first.
- All seven prepared commands require publication to main and parent authorization.
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

Verified: 106 passed, 4 SDK deprecation warnings. New support tests first failed
because the qualification module did not exist, then passed. Full changed suite
before the additional six parameterized support checks: 517 passed, 7 failed;
clean baseline: 512 passed, the **same 7 failures**. Final changed full suite:
524 passed, 7 identical baseline failures, 16 SDK deprecation warnings. The seven
new qualification shell blocks also pass `bash -n`. Failures are the undefined
activity variable, four existing incomplete offline DB mocks, and two stale
workflow expectations omitting `gate_watchdog`. These failures were not hidden
or weakened. `git diff --check` passes.

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
