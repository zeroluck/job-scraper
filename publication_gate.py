"""Verify pipeline results and finalize an immutable publication generation."""

import argparse
import os
from pathlib import Path

import config


PIPELINE_JOBS = ("scrape", "freehire_compat")
PUBLICATION_SCHEMA_VERSION = "freehire-publication-v1"

#: Table-driven alerting for deferred publication gates. A deferred gate with
#: blocking requirements means the watermark is frozen and no new discovery
#: cycles are created, so every subsequent hourly run is a no-op until a
#: human reviews the blocking tasks. These helpers surface that state as a
#: workflow warning, a step summary, and job outputs consumed by the
#: gate_watchdog workflow job (auto-filed GitHub issue). Alerting never
#: fails the gate itself.
GATE_WATCHDOG_ISSUE_LABEL = "pipeline-gate"
MAX_BLOCKING_DETAILS = 10


def _get_db():
    from supabase import create_client

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("Supabase URL and Key must be set in environment variables or config.")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def verify_pipeline_results(results: dict[str, str]) -> None:
    failures = {
        name: results.get(name, "missing")
        for name in PIPELINE_JOBS
        if results.get(name) != "success"
    }
    if failures:
        detail = ", ".join(f"{name}={result}" for name, result in failures.items())
        raise RuntimeError(f"Publication gate blocked: pipeline jobs did not succeed ({detail})")


def _count(db, table: str, filters: tuple[tuple[str, object], ...] = ()) -> int:
    query = db.table(table).select("job_id", count="exact")
    for field, value in filters:
        query = query.eq(field, value)
    response = query.limit(1).execute()
    if response.count is None:
        raise RuntimeError("Production count query did not return an exact count")
    return response.count


def _count_not_null(db, table: str, field: str, filters=()) -> int:
    query = db.table(table).select("job_id", count="exact")
    for filter_field, value in filters:
        query = query.eq(filter_field, value)
    response = query.not_.is_(field, None).limit(1).execute()
    if response.count is None:
        raise RuntimeError("Production count query did not return an exact count")
    return response.count


def query_publication_state(db=None) -> dict[str, int | str | None]:
    db = db or _get_db()
    jobs = config.SUPABASE_TABLE_NAME
    counts: dict[str, int | str | None] = {
        "total": _count(db, jobs, (("provider", "linkedin"),)),
        "current": _count(
            db, jobs, (("provider", "linkedin"), ("freehire_compat_status", "current"))
        ),
        "pending": _count(
            db, jobs, (("provider", "linkedin"), ("freehire_compat_status", "pending"))
        ),
        "failed": _count(
            db, jobs, (("provider", "linkedin"), ("freehire_compat_status", "failed"))
        ),
        "processing": _count(
            db, jobs, (("provider", "linkedin"), ("freehire_compat_status", "processing"))
        ),
        "prior_publication": _count_not_null(
            db, jobs, "freehire_compat_classified_at", (("provider", "linkedin"),)
        ),
        # public.freehire_jobs is the per-row publication gate. A historical
        # pending/failed backlog is reported above but does not block current rows.
        "published": _count(db, "freehire_jobs"),
        "scrape_watermark": None,
    }
    # The service-role-only view is the row contract itself. A current row
    # absent from it is stale/incomplete; every counted published row passed
    # all view predicates without duplicating that contract in Python.
    counts["stale"] = int(counts["current"]) - int(counts["published"])
    try:
        response = (
            db.table("scrape_run_state")
            .select("last_successful_scrape_at")
            .eq("id", 1)
            .limit(1)
            .execute()
        )
        if response.data:
            counts["scrape_watermark"] = response.data[0].get("last_successful_scrape_at")
    except Exception as exc:  # The watermark contract predates some deployments.
        print(f"Scrape watermark unavailable: {exc}")
    return counts


def validate_publication_state(
    state: dict[str, int | str | None], *, require_legacy_ready: bool = True
) -> None:
    current = int(state["current"] or 0)
    published = int(state["published"] or 0)
    if published > current:
        raise RuntimeError(
            f"Publication gate blocked: published={published} exceeds current={current}"
        )
    if require_legacy_ready and not state.get("scrape_watermark"):
        raise RuntimeError("Publication gate blocked: scrape watermark is absent")
    if require_legacy_ready and published == 0:
        raise RuntimeError("Publication gate blocked: zero published rows")


def finalize_publication(
    db,
    state: dict[str, int | str | None],
    discovery_cycle_id: int | None = None,
) -> dict[str, int | str | None]:
    if discovery_cycle_id is None:
        watermark = state.get("scrape_watermark")
        if not isinstance(watermark, str) or not watermark:
            raise RuntimeError("Publication finalization requires a non-null scrape watermark")
        rpc_name = "finalize_freehire_publication"
        rpc_args = {"p_source_scrape_watermark": watermark}
    else:
        if discovery_cycle_id <= 0:
            raise RuntimeError("Publication finalization requires a positive discovery cycle ID")
        rpc_name = "finalize_freehire_publication_v2"
        rpc_args = {"p_cycle_id": discovery_cycle_id}
    response = db.rpc(rpc_name, rpc_args).execute()
    rows = response.data or []
    if isinstance(rows, dict):
        publication = rows
    elif len(rows) == 1 and isinstance(rows[0], dict):
        publication = rows[0]
    else:
        raise RuntimeError("Publication finalization did not return exactly one state row")

    outcome = publication.get("outcome") if discovery_cycle_id is not None else "published"
    if outcome == "deferred":
        return {
            "outcome": "deferred",
            "reason": str(publication.get("reason") or "publication deferred"),
            "requested_cycle_id": discovery_cycle_id,
            "eligible_cycle_id": publication.get("eligible_cycle_id"),
            "blocking_count": int(publication.get("blocking_count") or 0),
            "generation": None,
            "published_at": None,
            "source_scrape_watermark": publication.get("source_scrape_watermark")
            or state.get("scrape_watermark"),
            "row_count": None,
            "schema_version": PUBLICATION_SCHEMA_VERSION,
        }
    if outcome not in {"published", "unchanged"}:
        raise RuntimeError(f"Publication finalization returned an invalid outcome ({outcome!r})")
    generation = publication.get("generation")
    row_count = publication.get("row_count")
    returned_watermark = publication.get("source_scrape_watermark")
    published_at = publication.get("published_at")
    schema_version = publication.get("schema_version")
    if not isinstance(generation, int) or generation <= 0:
        raise RuntimeError("Publication finalization returned an invalid generation")
    if not isinstance(row_count, int) or row_count < 0:
        raise RuntimeError("Publication finalization returned an invalid row count")
    if discovery_cycle_id is None and returned_watermark != watermark:
        raise RuntimeError(
            "Publication finalization returned a different scrape watermark "
            f"({returned_watermark!r} != {watermark!r})"
        )
    if not isinstance(published_at, str) or not published_at:
        raise RuntimeError("Publication finalization returned an invalid publication time")
    if schema_version != PUBLICATION_SCHEMA_VERSION:
        raise RuntimeError(
            "Publication finalization returned an unsupported schema version "
            f"({schema_version!r})"
        )
    result = {
        "generation": generation,
        "published_at": published_at,
        "source_scrape_watermark": returned_watermark,
        "row_count": row_count,
        "schema_version": schema_version,
    }
    if discovery_cycle_id is not None:
        result.update({
            "outcome": outcome,
            "reason": publication.get("reason"),
            "requested_cycle_id": discovery_cycle_id,
            "eligible_cycle_id": publication.get("eligible_cycle_id", discovery_cycle_id),
            "blocking_count": 0,
        })
    return result


def prune_publication_generations(db) -> int:
    """Prune at most one expired generation outside the publish transaction."""
    response = db.rpc(
        "prune_freehire_publication_generations",
        {"p_keep_generations": 3, "p_max_generations": 3},
    ).execute()
    value = response.data
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, dict):
        value = value.get("prune_freehire_publication_generations")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimeError("Publication pruning returned an invalid deletion count")
    return value


def try_prune_publication_generations(db) -> int:
    """Best-effort retention maintenance after an atomic publication commit."""
    try:
        return prune_publication_generations(db)
    except Exception as exc:
        print(f"Publication pruning deferred: {exc}")
        return 0


def write_github_outputs(state: dict[str, int | str | None], output_path: str | None) -> None:
    if not output_path:
        return
    lines = []
    for key, value in state.items():
        text = "" if value is None else str(value)
        if "\n" in text or "\r" in text:
            raise ValueError(f"Unsafe multiline GitHub output for {key}")
        lines.append(f"{key}={text}\n")
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.writelines(lines)


def query_blocking_requirements(db, discovery_cycle_id: int) -> list[dict]:
    """Return unaccepted blocking requirement details for a deferred cycle.

    Each entry keeps the requirement filed as failing (status, attempts, and
    error code are reported, never mutated): task_id, provider,
    source_job_id, task_kind, requirement_key, status, attempt_count,
    max_attempts, last_error_code, and latest_observed_at.
    """
    req_response = (
        db.table("linkedin_discovery_requirements")
        .select("discovery_cycle_id,ingestion_run_id,provider,source_job_id,task_kind,requirement_key,task_id")
        .eq("discovery_cycle_id", discovery_cycle_id)
        .eq("required", True)
        .execute()
    )
    requirements = req_response.data or []
    if not requirements:
        return []
    acc_response = (
        db.table("linkedin_discovery_requirement_acceptances")
        .select("discovery_cycle_id,ingestion_run_id,provider,source_job_id,task_kind,requirement_key")
        .eq("discovery_cycle_id", discovery_cycle_id)
        .execute()
    )
    accepted = {
        (
            row.get("ingestion_run_id"),
            row.get("provider"),
            row.get("source_job_id"),
            row.get("task_kind"),
            row.get("requirement_key"),
        )
        for row in (acc_response.data or [])
    }
    blocking = []
    for req in requirements:
        key = (
            req.get("ingestion_run_id"),
            req.get("provider"),
            req.get("source_job_id"),
            req.get("task_kind"),
            req.get("requirement_key"),
        )
        if key in accepted:
            continue
        task_response = (
            db.table("linkedin_discovery_tasks")
            .select("id,status,attempt_count,max_attempts,last_error_code,latest_observed_at")
            .eq("id", req.get("task_id"))
            .limit(1)
            .execute()
        )
        task_rows = task_response.data or []
        task = task_rows[0] if task_rows else {}
        if task.get("status") in ("complete", "terminal_unavailable"):
            continue
        blocking.append({
            "task_id": req.get("task_id"),
            "provider": req.get("provider"),
            "source_job_id": req.get("source_job_id"),
            "task_kind": req.get("task_kind"),
            "requirement_key": req.get("requirement_key"),
            "ingestion_run_id": req.get("ingestion_run_id"),
            "status": task.get("status"),
            "attempt_count": task.get("attempt_count"),
            "max_attempts": task.get("max_attempts"),
            "last_error_code": task.get("last_error_code"),
            "latest_observed_at": task.get("latest_observed_at"),
        })
        if len(blocking) >= MAX_BLOCKING_DETAILS:
            break
    return blocking


def format_blocking_warning(discovery_cycle_id: int, blocking: list[dict]) -> str:
    first = blocking[0]
    return (
        f"Publication gate deferred: cycle {discovery_cycle_id} blocked by "
        f"{len(blocking)} unaccepted requirement(s); first task={first.get('task_id')} "
        f"status={first.get('status')} error={first.get('last_error_code')} "
        f"{first.get('provider')}:{first.get('source_job_id')}"
    )


def format_blocking_summary(discovery_cycle_id: int, reason: str | None, blocking: list[dict]) -> str:
    lines = [
        "## Publication gate deferred",
        "",
        f"- requested cycle: `{discovery_cycle_id}`",
        f"- reason: {reason or 'publication deferred'}",
        f"- unaccepted blocking requirements: {len(blocking)}",
        "",
        "| task | source | status | attempts | error | last observed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in blocking:
        attempts = f"{item.get('attempt_count')}/{item.get('max_attempts')}"
        lines.append(
            f"| {item.get('task_id')} "
            f"| {item.get('provider')}:{item.get('source_job_id')} "
            f"| {item.get('status')} | {attempts} "
            f"| {item.get('last_error_code')} | {item.get('latest_observed_at')} |"
        )
    lines += [
        "",
        "Unblock with a reviewed acceptance (records reviewer + reason, keeps the",
        "failing task row intact):",
        "",
        "```sql",
        "SELECT public.accept_linkedin_discovery_requirement(",
        f"  {discovery_cycle_id}, '<ingestion_run_id>', '<provider>',",
        "  '<source_job_id>', '<task_kind>', '<requirement_key>',",
        "  '<reviewer>', '<reason>');",
        "```",
    ]
    return "\n".join(lines)


def append_github_summary(markdown: str, summary_path: str | None) -> None:
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(markdown + "\n")


def emit_deferral_warning(db, state: dict[str, int | str | None]) -> str:
    """Warn (never fail) about a deferred gate with blocking requirements.

    Returns a single-line blocking-details string for GitHub outputs ("" when
    there is nothing actionable to report).
    """
    try:
        cycle_id = state.get("requested_cycle_id")
        if state.get("outcome") != "deferred" or not cycle_id:
            return ""
        blocking = query_blocking_requirements(db, int(cycle_id))
        if not blocking:
            return ""
        warning = format_blocking_warning(int(cycle_id), blocking)
        print(f"::warning::{warning}")
        append_github_summary(
            format_blocking_summary(int(cycle_id), state.get("reason"), blocking),
            os.getenv("GITHUB_STEP_SUMMARY"),
        )
        first = blocking[0]
        return (
            f"task={first.get('task_id')} status={first.get('status')} "
            f"error={first.get('last_error_code')} "
            f"{first.get('provider')}:{first.get('source_job_id')} "
            f"({len(blocking)} blocking)"
        )
    except Exception as exc:
        print(f"Gate deferral warning unavailable: {exc}")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    for job in PIPELINE_JOBS:
        parser.add_argument(f"--{job.replace('_', '-')}-result", required=True)
    parser.add_argument("--discovery-cycle-id", type=int, required=True)
    args = parser.parse_args()
    results = {
        "scrape": args.scrape_result,
        "freehire_compat": args.freehire_compat_result,
    }
    verify_pipeline_results(results)
    db = _get_db()
    state = query_publication_state(db)
    validate_publication_state(state, require_legacy_ready=False)
    state.update(finalize_publication(db, state, args.discovery_cycle_id))
    pruned_generations = (
        try_prune_publication_generations(db)
        if state["outcome"] in {"published", "unchanged"}
        else 0
    )
    state["blocking_details"] = emit_deferral_warning(db, state)
    print(
        "Publication state: "
        f"total={state['total']} current={state['current']} pending={state['pending']} "
        f"failed={state['failed']} processing={state['processing']} stale={state['stale']} "
        f"published={state['published']} prior_publication={state['prior_publication']} "
        f"scrape_watermark={state['scrape_watermark'] or 'unavailable'} "
        f"outcome={state['outcome']} reason={state['reason'] or 'none'} "
        f"requested_cycle_id={state['requested_cycle_id']} "
        f"eligible_cycle_id={state['eligible_cycle_id'] or 'none'} "
        f"blocking_count={state['blocking_count']} "
        f"blocking_details={state.get('blocking_details') or 'none'} "
        f"generation={state['generation']} published_at={state['published_at']} "
        f"schema_version={state['schema_version']} row_count={state['row_count']} "
        f"pruned_generations={pruned_generations}"
    )
    write_github_outputs(state, os.getenv("GITHUB_OUTPUT"))


if __name__ == "__main__":
    main()
