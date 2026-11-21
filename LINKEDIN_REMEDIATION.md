# LinkedIn remediation — 2026-11-21

## Authority and decisions

This session is authorized to commit/push, deploy qualified narrow fixes, and
run bounded canaries/backlog drains. The user explicitly chose to **preserve the
strict publication contract**. Historical debt acceptance and coverage-loss
acceptance are not authorized.

Native authority: `https://pgsql.jdb.l.cd`, SSH `proxmox`, CT337, database `jobs`,
OID `299919`, system identifier `7701229561420400865`. Storage remains separately
configured Supabase Storage. Administrative operations must check all three
database identity values inside their transaction.

## Baseline and acceptance ledger

Fresh guarded read at `2026-11-21T19:42:57Z`:

| Measure | Before |
| --- | ---: |
| Selected sealed cycle / sequence | 70 / 70 |
| Ready detail tasks | 714 (703 pending, 11 retryable) |
| Leased tasks | 0 |
| Unsatisfied requirements / distinct tasks | 1,184 / 714 |
| Classification current / pending / failed / processing | 34,048 / 105 / 12 / 0 |
| LinkedIn canonical jobs | 34,165 |
| Immutable generation / rows / source cycle | 71 / 23,745 / 49 |
| Immutable publication timestamp | 2026-10-09T05:55:59.480245Z |
| Strict source watermark | 2026-09-30T10:53:12.315752Z |
| Failed predecessors / expired debt | 50, 51 / 65 |

Acceptance is incremental:

1. Continuation derives from the exact prior sealed scope and contiguous page
   proof, not execution completion. Regression spans: 7, 14, 48 hours. Missing
   page proof fails closed. Existing execution timestamps retain their meaning.
2. Budget-deferred, rate-limited, challenged, failed, and completed executions
   export exact cycle identity and distinct outcomes. Bounded search deferral
   permits independent classification. Source denials remain alertable.
3. Claiming does not charge a source attempt. The first source grant per live
   lease charges once; physical retries retain individual attempt evidence.
   Local grant refusal releases the lease without spending source allowance.
4. Retry-only queues use the same actionable-count RPC in manual preflight and
   execution. Task ceiling remains 300. Canary physical/runtime inputs narrow
   the existing budget; no new search or classifier is added to manual drains.
5. Shared cooldown survives process restarts. Starting effective spacing is
   5 seconds. A 429 doubles spacing up to 60 seconds and persists a 60-second
   exponential cooldown (up to one hour), extended by Retry-After up to seven
   days. Twenty successful responses permit only a 10% recovery, with a
   5-second floor. This is an empirical starting policy, not a vendor quota.
6. Every adaptive HTTP retry requires a grant and details require a live lease.
   Redirect following is disabled so one grant cannot hide additional sends.
   A durable 429 yields the invocation rather than amplifying retries.
7. Zero actionable work/leases, real canonical/listing linkage, and retained
   404/410 evidence are required for detail completion. Task applications,
   distinct source IDs, distinct canonical IDs, and canonical inserts must be
   reported separately from persisted evidence.
8. Classification must settle pending/processing cohorts, retain attempt
   history, and identify every residual failure. The physically enforced LLM
   invocation budget remains in effect.
9. Strict publication remains blocked until qualified historical recovery or
   a later explicit product decision. A green workflow and current view count
   do not satisfy immutable-publication acceptance.

## Migration and role qualification

The five forwards were applied atomically to native CT337 at
`2026-11-21T20:11:38Z`, with database identity, exact prior function hashes,
selected cycle70/sequence70, closed circuit, zero leases, and zero active/queued
workflows checked immediately before application. Actual `job_runner` readback
returned the same 714 actionable tasks, 1,184 requirements, 65 expired debt, and
generation71. Receipt: `linkedin-remediation-deploy-20261121T201138Z.json` in the
session's protected temporary evidence directory.

Apply only the five incremental files, in order:

1. `supabase_setup/reconcile_linkedin_actionable_selector.sql`
2. `supabase_setup/repair_linkedin_continuation.sql`
3. `supabase_setup/repair_linkedin_retry_accounting.sql`
4. `supabase_setup/linkedin_durable_throttling.sql`
5. `supabase_setup/linkedin_publication_diagnostics.sql`

The companion history mirror concatenates those exact files:
`job-scraper-web/supabase/migrations/20261121195836_linkedin_ingestion_remediation.sql`.
The manifest preserves the hosted historical ledger explicitly as historical;
CT337 currently has no migration-history table. Record native application
timestamps, identity, file digests, and role readback separately. Do not invent
hosted application stamps or replay consolidated schema files over native SQL.

`tests/test_linkedin_native_remediation.py` restores a fresh schema-only native
capture into network-isolated PostgreSQL 17.11, preserving function owners,
ACLs, and RLS policies. It exercises actual `job_runner` calls, anonymous-role
denial, source-attempt accounting, retry-only selection, cooldown across separate
processes/connections, duplicate-feedback idempotency, and the challenge circuit.
Migrations are reapplied to verify idempotency. This is distinct from a live
Data API/workflow canary, which is also required before operational acceptance.

Local whole-suite qualification: 682 passed, 12 skipped, six existing failures
reproduced individually against deployed-source worktree `7ffa7a3`. Those are
the disabled job-manager undefined `response_text_lower`, four legacy tests
with incomplete database doubles, and Python 3.14's strict private-CA fixture.
New focused tests and the isolated native-role qualification pass separately.

## Bounded operations

Initial application release: `9b88fed27ec7b7cd3a8659e8934cf027dd3d7ba5`.
Companion migration mirror: `9931abf59fb6c95e6b865906b35f51afc6087b75`.
Both repositories' migration-drift Actions checks passed.

The first SDK preflight, run `44945429211`, correctly stopped before source
traffic with `PGRST202`. Native `db-channel-enabled=false` means SQL NOTIFY does
not refresh this service's schema cache. After fresh identity/lease/workflow
checks, SIGUSR1 was sent only to the main process of
`jobs-postgrest-native.service` at `2026-11-21T20:19:04Z`. PID304 and service
start time remained unchanged; no restart or credential/configuration change
was performed. Subsequent actual GitHub `job_runner` SDK preflights passed.
Future native schema deployments must include this schema-only reload and
actual Data API readback; administrative SQL alone is insufficient.

Live source qualification through `2026-11-21T20:25:27Z`:

| Run | Physical detail HTTP outcomes | Persisted outcome |
| --- | --- | --- |
| 44945630179 | one 429 | yielded; 60-second shared cooldown; spacing 5→10 seconds |
| 44945821681 | six 200, one 429 | six applications; yielded; 120-second cooldown; spacing 10→20 seconds |

Each physical attempt has a durable grant/lease-attempt row. Both runs retained
cycle70/sequence70, released all leases, and recorded runner/release/response
headers. The first six applications cover six distinct source IDs and six
canonical IDs, including four new canonical inserts. Broken listing linkage:
zero. Remaining cohort: 696 pending +12 retryable =708; the momentary ready
count excludes any future retry until its availability timestamp.

These canaries demonstrate bounded feedback and successful ingestion, **not**
yet low-429 sustainable throughput. Do not increase dispatch frequency or
concurrency on this evidence.

The 12 inherited classification failures were freshly reviewed: six recorded
provider429, six provider503, durable attempt counts6–9. All are excluded by the
normal cap6. The manual classifier now exposes a physical request budget and
a supported, invocation-local cap10 eligibility override. Use that override
only after a healthy provider canary; it preserves all prior attempt counts.
Shared provider-pool failures stop later batches/pages instead of amplifying
calls across the invocation.

Before each dispatch re-read cycle/sequence, actionable work, leases, cooldown,
circuit, configuration, release SHA, and active/queued workflows. Use the
existing `linkedin-freehire-pipeline` global concurrency group.

Start manual scraper-only qualification with `http_attempt_limit=10` and
`runtime_seconds=120`; inspect persisted grants, canonical applications, task
states, and 429 rate. Repeat a small canary before choosing a larger bounded
batch. A 429 yields the run and extends the shared policy. Respect that state;
do not reset it or reset task counters. The ordinary 300-task ceiling remains.

## Historical target ledger

`linkedin_historical_targets.json` freezes six exact periods across every one
of the 13 original parent definitions, pinned by SHA-256 to unchanged
`recovery_parameters.json`. The Cartesian product defines **78 individually
identified scope-period targets**, not 65 debt rows.

H1–H3: specific remaining source boundary. Cycle56 observed 2,221 distinct IDs,
finished discovered details, and reportedly inserted 527 canonical jobs; it
does not establish exhaustive historical inventory. Every parent stopped at
offset 250. Guest endpoint time filters have no qualified historical upper
bound. DD sorting, interactive pagination, and work-mode facets have not
established an exhaustive alternative.

N1–N3: remaining recoverable search work with unproven inventory. These are
interval holes in completed window proof, not measured missed-job counts.
Any new continuity audit findings must be appended, preserving old targets.

The uncommitted all-parent enumeration candidate was inspected and preserved:
416/416/520 planned units, durable local checkpoints, evidence-only output,
unverified work-mode semantics, no ingestion/debt authority. Its frozen August
7 anchor now exceeds its 100-day horizon. It requires explicit requalification;
passing earlier tests or moving the anchor does not authorize execution.

No new expired-debt resolver is justified until qualified evidence exists. The
supported recovery design must take explicit debt IDs, prove exact parent and
interval containment, require page/observation and canonical outcomes, preserve
original intervals, and retain an auditable resolution receipt. Broad capped
searches alone cannot supply that proof.

## Health and sustained-operation criteria

`scripts/linkedin_health.py` measures requested versus recorded 7-day dispatches,
run-start metadata delay, covered-through age, classification pending/claim
age, actionable/leased work, and immutable publication age. Initial warning
thresholds are 80% dispatch delivery, 36-hour search coverage, 24-hour pending
classification/publication, and 30-minute classifier claims. These are explicit
operational thresholds, not claims of an already achieved SLO. Pending
classification age currently uses canonical `first_seen_at`; it is explicitly
labelled as a proxy because time entering pending status is not persisted.

Gate diagnostics report predecessor IDs, exact requirement/distinct-task/debt
counts, capped examples, and actual immutable generation metadata even after
upstream interruption. The compatibility view count is labelled
`current_view_rows`, not a fresh generation count.

Multiple consecutive completed cycles and independent dispatch monitoring are
still required. A watchdog running only when Actions dispatches cannot detect
its own total scheduling outage. Run the read-only health collector from a
separately monitored scheduler before claiming sustained dispatch reliability.
Run-start timestamps do not establish runner-job queue delay or the cause of
missing schedule events. Analyzer/scorer/job-manager/resume workflows require
their own native-write qualification before enabling.
