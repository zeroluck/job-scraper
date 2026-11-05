# Historical recovery candidate (not activated)

Base: `1bb436d8129818ae0df777bfa345c8a4af288d6b`.

## Execution order — do not combine these stages

1. On an isolated full-copy authority first, use the existing `.github/workflows/scraper_only_manual.yml` (or its exact local steps) for the independently read **current sealed cycle ID and discovery sequence**. The original audit's cycle54 is not a fixed current identity; an isolated rehearsal's cycle55 must not be confused with production cycle55. Keep `LINKEDIN_HISTORY_RECOVERY` unset and `SCRAPE_CONFIG_SOURCE=db`. Set `LINKEDIN_DETAIL_ONLY_CYCLE_ID` and `LINKEDIN_DETAIL_ONLY_SEQUENCE` to that exact sealed identity. Run `python scripts/preflight_scraper_only.py`, then `python scraper.py`. The existing guard runs again after the actual resume selector. Each invocation keeps the original 300-task ceiling. Inspect exact queue/lease/source-gate state after each batch. The audit's 581 pending tasks are not a fixed current count, and two batches are not guaranteed to finish them.
2. Independently verify no pending, leased or retryable global tasks remain and the selector no longer returns a resumable cycle. Do not accept or resolve historical failures/debt to force this transition. `new` mode enforces absence of a resumable cycle and a zero exact global count immediately before original scope preparation. Non-GitHub writers must also be excluded: workflow concurrency is not a database-wide lock.
3. Export the **complete actual configuration** with the executable below. The sole local change is `settings.options.outage_recovery_cap_hours=2160`; no configuration RPC write exists in this candidate. Set the matching manual override; raising the cap alone is insufficient.

   ```sh
   python history_recovery.py --output "$RECOVERY_CONFIG"
   export SCRAPE_CONFIG_SOURCE=file SCRAPE_CONFIG_FILE="$RECOVERY_CONFIG"
   export LINKEDIN_DISCOVERY_MODE=adaptive_queue SCRAPE_ARCHETYPE=''
   export LINKEDIN_RECOVERY_LOOKBACK_HOURS=2160
   export LINKEDIN_HISTORY_TARGETS=recovery_parameters.json
   export LINKEDIN_HISTORY_RECOVERY=new
   unset LINKEDIN_DETAIL_ONLY_CYCLE_ID LINKEDIN_DETAIL_ONLY_SEQUENCE
   python scraper.py
   ```

   `JOB_DATA_API_URL` / `JOB_DATA_API_TOKEN` must identify the authorized isolated authority for the first real-GET rehearsal; never make production credentials available there. Existing private-CA and separate retained Storage settings remain necessary. The candidate workflow deliberately requires `vars.JOB_DATA_API_URL` rather than installing a deployment endpoint. No workflow has been published or dispatched.
4. Read back the real new cycle ID/sequence, complete scope definitions and posted-time windows. In `new` mode only, the create RPC's incomplete response is hydrated by a second call to the **original resume selector**, before the unchanged manifest guard. Both positive integer cycle ID and discovery sequence must match the create response exactly and exceed54. Missing/stale readback, missing definitions, changed/duplicate scope keys, or changed returned scope fields/windows fail closed; definitions are never copied from requested manifests. The runtime guard still rejects missing/extra scopes, mismatched audited definitions, any effective truncation later than an original gap, or a window not containing every original gap. All checks precede the source gate. A rejected readback/manifest can leave a created cycle; inspect rather than replaying blind.
5. For the **same** broad manifest in later bounded invocations, use `LINKEDIN_HISTORY_RECOVERY=resume`, `LINKEDIN_HISTORY_CYCLE_ID=<exact new ID>` and `LINKEDIN_HISTORY_SEQUENCE=<exact new sequence>`. Repeat the full actual configuration export using a new local path. Missing or wrong resume identities fail; they never silently create a replacement cycle. Keep the same global workflow concurrency group `linkedin-freehire-pipeline`. A budget-limited successful process is not completed coverage.

The manual candidate workflow implements stages3–5 only, using `python scraper.py`. It has no schedule, classification job, LLM credentials, publication-gate job or watchdog. Stage1 remains the existing reviewed drain workflow, not a repurposed broad cycle54.

## Budgets and unchanged behavior

For the actual revision10 export: 800 physical search HTTP attempts, 800 physical detail HTTP attempts (at most1,600 combined), 300 detail tasks, 1,620s search +300s detail =1,920s internal deadline envelope; workflow timeout40min. Source retries consume the existing physical counters. Normal durable request grants, pacing, challenge/circuit policy, heartbeat, leases, global claimer, original canonical persistence and source parsing stay intact. These are per-invocation ceilings, not a total recovery cost authorization. Inspect each invocation before repeating. No custom source transport or fabricated response is installed.

Original page-exhaustion semantics are preserved: only recognized source `no_results` exhausts a scope. Budget/runtime interruptions remain resumable; nonempty cards are never truncated or relabeled empty. Offline regression exercises 13 scopes with21 nonempty pages each followed by the22nd empty page (286 requests), plus a13-request interrupted case that must not finish/seal any scope.

## Pagination / historical completeness blockers

- The audit described configured hard_max_pages_per_query20 (validator100). In this pinned exhaustive implementation those settings populate planning metadata; the actual scheduler does **not** stop at20 or100. Do not raise those options or pretend that setting them would solve pagination. The regression crosses20 under the unchanged code.
- The real effective local limits are physical attempts and wall-clock time. A90-day search can require several resumed invocations. If upstream repeats nonempty pages, the source ceiling/runtime still stops the invocation without manufacturing exhaustion.
- An upstream guest-search result/offset cap, ranking omission or retention limit is a genuine coverage blocker, even when a recognized empty page appears at that cap. The prior single90-day GET proves useful old postings for one scope only. No numeric upstream maximum, all-scope90-day retention, runner-egress equivalence or absence of a cap has been qualified here. A terminal empty guest page proves observed result-set exhaustion, **not** historical inventory completeness. A future rehearsal must retain all real offsets/source IDs/posting dates and investigate saturation/repetition/early emptiness; it must not certify the three original gaps from a broad manifest alone.
- No upper posted-time source bound exists in the original endpoint. This is an intentional broad superset search anchored early enough to include September15, not invented exact from/to search support.
- Deleted/delisted jobs cannot be promised recoverable. This candidate offers real best-effort retrieval, not a waiver or a historical completeness assertion.

## Debt and rollback

No SQL, debt-acceptance/reconciliation path or watermark bypass was added. All production debt/configuration/jobs/watermarks remain untouched by preparation and tests. Future authorized execution of the original scraper is **not read-only**: normal scope preparation can expire pending debt; scope finish resolves eligible pending debt; existing sealing, operational watermarks and eligible-failed-cycle logic retain their original effects. Original expired_unresolved rows are not converted to recovered/accepted by this candidate. It does not implement the separately reviewed provenance-backed expired-debt recovery path described by the audit. Capture all original debt rows and verify them independently before/after a real rehearsal. If byte-for-byte no debt changes during execution is required, the original entrypoint cannot meet that requirement without a separately qualified DB contract; do not silently call its mutating preparation helper read-only.

Before activation, rollback is deletion of this isolated candidate and local exports; no production reversal is necessary. After any future real execution, unset recovery variables and use DB configuration/original release to stop further recovery, but retain the real cycle/pages/tasks/jobs and original debt for review. Code/config rollback does not undo committed data, global lease reclamation, source grants/timing, canonical merges, normal debt changes or watermarks. Never delete recovered rows or reset debt/watermarks as an automatic rollback. Any data restoration requires a fenced, separately authorized checkpoint reconciliation, including downstream effects.

## Verification

The isolated real-GET rehearsal drained its sealed predecessor, then created cycle55 and failed safely before source GETs because the actual create RPC omitted every scope definition. An independently guarded exact resume of that same isolated cycle performed bounded ingestion; it did not qualify `new` mode. The hydration follow-up has observed RED/GREEN tests and113 passing focused cases, including unchanged 300/301 task-boundary checks. Offline replay of the retained real create/selector envelopes passes all13 definitions and39 original intervals. This is not a fresh native-service or real-GET qualification of the fixed `new` path; require that separate acceptance before activation. Ordinary discovery and exact resume do not perform the added readback. No SQL, scheduler, debt or source-gate changes were made.

Initial candidate verification, before the budget and hydration follow-ups: new behavior was developed through observed failing tests, then passing tests. Focused gate:69 passed (29 new cases plus40 existing discovery/manual-drain/entrypoint cases). Full suite:579 passed,7 failed,17 warnings; unchanged pinned base:550 passed, the **same7 failed**,17 warnings. Failures are an existing `response_text_lower` NameError, four tests reaching an inert data hostname, and two stale hourly-workflow assertions. A smaller existing environment lacked pdfplumber; the full suite was rerun with the complete existing environment rather than modifying shared dependencies.

The protected qualification receipt contains the freshly identity-guarded READ ONLY full configuration export and an offline original `_scope_manifest` exercise using all actual13 current scope definitions. Only the local cap changed; all39 target intervals passed containment; earliest generated source window was2026-08-06T03:26:05.193427+00:00. This is explicitly an offline boundary test, not a new database manifest or a live ingestion/recovery claim.
