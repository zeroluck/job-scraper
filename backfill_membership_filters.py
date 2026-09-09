"""Re-evaluate explicitly targeted membership filters. Dry-run by default."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import config
import supabase_utils
from lane_catalog import CANONICAL_LANE_SLUGS
from scrape_configuration import (
    ScrapeConfiguration,
    expand_location_scopes,
    load_scrape_configuration,
    parse_scrape_configuration,
)
from scraper import _career_lane_runtime_profile


MEMBERSHIP_SELECT = (
    "job_id,archetype,filter_status,is_filtered,filter_reason,"
    "jobs!inner(job_id,job_title,company,description)"
)


class ConfigurationRevisionMismatch(RuntimeError):
    pass


def _get_db():
    from supabase import create_client

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("Supabase URL and service-role key must be configured.")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def _load_configuration(db: Any, config_json: Path | None) -> ScrapeConfiguration:
    if config_json is None:
        return load_scrape_configuration(db=db)
    try:
        payload = config_json.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Could not read configuration file '{config_json}': {exc}") from exc
    return parse_scrape_configuration(payload, source=str(config_json))


def _verify_revision(configuration: ScrapeConfiguration, expected_revision: int) -> None:
    if configuration.revision != expected_revision:
        raise ConfigurationRevisionMismatch(
            "Scrape configuration revision mismatch: "
            f"expected {expected_revision}, got {configuration.revision}."
        )


def _runtime_profiles(
    configuration: ScrapeConfiguration, archetypes: Iterable[str]
) -> dict[str, dict]:
    lanes = {lane.archetype: lane for lane in configuration.lanes}
    profiles = {}
    for archetype in archetypes:
        lane = lanes[archetype]
        geographies = expand_location_scopes(lane.locations)
        location = geographies[0].location if geographies else ""
        profiles[archetype] = _career_lane_runtime_profile(lane, location)
    return profiles


def fetch_memberships(
    db: Any, archetypes: Iterable[str], page_size: int = 1000
) -> list[dict]:
    targeted = sorted(set(archetypes))
    rows: list[dict] = []
    offset = 0
    while True:
        response = (
            db.table("job_archetype_memberships")
            .select(MEMBERSHIP_SELECT)
            .in_("archetype", targeted)
            .order("archetype")
            .order("job_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        if not isinstance(page, list):
            raise RuntimeError("Membership query returned a non-list response.")
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return rows


def _joined_job(row: dict) -> dict:
    job = row.get("jobs")
    if isinstance(job, list):
        if len(job) != 1:
            raise RuntimeError(
                f"Membership {row.get('job_id')!r} did not join to exactly one job."
            )
        job = job[0]
    if not isinstance(job, dict):
        raise RuntimeError(f"Membership {row.get('job_id')!r} has no joined job.")
    if str(job.get("job_id")) != str(row.get("job_id")):
        raise RuntimeError(f"Membership {row.get('job_id')!r} joined to the wrong job.")
    return {
        "job_id": str(job["job_id"]),
        "job_title": job.get("job_title") or "",
        "company": job.get("company") or "",
        "description": job.get("description") or "",
    }


def evaluate_changes(rows: Iterable[dict], profiles: dict[str, dict]) -> list[dict]:
    changes = []
    for row in rows:
        lane = row.get("archetype")
        if lane not in profiles:
            raise RuntimeError(f"Fetched untargeted membership lane {lane!r}.")
        job = _joined_job(row)
        result = supabase_utils.evaluate_lane_filter(
            job,
            archetype=lane,
            runtime_profile=profiles[lane],
        )
        old = {
            "status": row.get("filter_status"),
            "is_filtered": row.get("is_filtered"),
            "reason": row.get("filter_reason"),
        }
        new = {
            "status": result["filter_status"],
            "is_filtered": result["is_filtered"],
            "reason": result["filter_reason"],
        }
        if old == new:
            continue
        changes.append({
            "job_id": str(row["job_id"]),
            "lane": lane,
            "title": job["job_title"],
            "old_status": old["status"],
            "new_status": new["status"],
            "old_is_filtered": old["is_filtered"],
            "new_is_filtered": new["is_filtered"],
            "old_reason": old["reason"],
            "new_reason": new["reason"],
        })
    return sorted(changes, key=lambda change: (change["lane"], change["job_id"]))


def _add_snapshot_filter(query: Any, field: str, value: Any) -> Any:
    if value is None:
        return query.is_(field, "null")
    return query.eq(field, value)


def apply_changes(db: Any, changes: Iterable[dict], chunk_size: int = 100) -> int:
    groups: dict[tuple, list[str]] = defaultdict(list)
    for change in changes:
        key = (
            change["lane"],
            change["old_status"],
            change["old_is_filtered"],
            change["old_reason"],
            change["new_status"],
            change["new_is_filtered"],
            change["new_reason"],
        )
        groups[key].append(change["job_id"])

    applied = 0
    for key in sorted(groups, key=lambda value: json.dumps(value, default=str)):
        lane, old_status, old_filtered, old_reason, status, is_filtered, reason = key
        job_ids = sorted(groups[key])
        payload = {
            "filter_status": status,
            "is_filtered": is_filtered,
            "filter_reason": reason,
        }
        for start in range(0, len(job_ids), chunk_size):
            chunk = job_ids[start:start + chunk_size]
            query = (
                db.table("job_archetype_memberships")
                .update(payload)
                .eq("archetype", lane)
                .in_("job_id", chunk)
            )
            query = _add_snapshot_filter(query, "filter_status", old_status)
            query = _add_snapshot_filter(query, "is_filtered", old_filtered)
            query = _add_snapshot_filter(query, "filter_reason", old_reason)
            response = query.execute()
            updated = response.data or []
            updated_ids = {str(row["job_id"]) for row in updated}
            if updated_ids != set(chunk):
                missing = sorted(set(chunk) - updated_ids)
                raise RuntimeError(
                    "Memberships changed concurrently or were not updated: "
                    + ", ".join(missing)
                )
            applied += len(chunk)
    return applied


def _transition_counts(changes: Iterable[dict]) -> dict[str, int]:
    counts = Counter(
        f"{change['old_status'] if change['old_status'] is not None else '<null>'}"
        f"->{change['new_status']}"
        for change in changes
    )
    return dict(sorted(counts.items()))


def run_backfill(
    db: Any,
    *,
    archetypes: Iterable[str],
    expected_revision: int,
    apply: bool = False,
    config_json: Path | None = None,
    page_size: int = 1000,
    write_chunk_size: int = 100,
) -> dict:
    targeted = sorted(set(archetypes))
    if not targeted:
        raise ValueError("At least one archetype must be explicitly targeted.")
    unknown = sorted(set(targeted) - set(CANONICAL_LANE_SLUGS))
    if unknown:
        raise ValueError("Unknown archetype(s): " + ", ".join(unknown))
    if apply and config_json is not None:
        raise ValueError("--config-json is restricted to dry-runs; --apply requires DB configuration.")
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000.")
    if not 1 <= write_chunk_size <= 500:
        raise ValueError("write_chunk_size must be between 1 and 500.")

    configuration = _load_configuration(db, config_json)
    _verify_revision(configuration, expected_revision)
    profiles = _runtime_profiles(configuration, targeted)
    memberships = fetch_memberships(db, targeted, page_size=page_size)
    changes = evaluate_changes(memberships, profiles)

    applied_count = 0
    if apply:
        current_configuration = load_scrape_configuration(db=db)
        _verify_revision(current_configuration, expected_revision)
        if current_configuration.model_dump(mode="json") != configuration.model_dump(mode="json"):
            raise ConfigurationRevisionMismatch(
                "Scrape configuration changed without a revision change during the backfill."
            )
        applied_count = apply_changes(db, changes, chunk_size=write_chunk_size)

    return {
        "mode": "apply" if apply else "dry-run",
        "configuration_revision": configuration.revision,
        "target_archetypes": targeted,
        "memberships_scanned": len(memberships),
        "change_count": len(changes),
        "applied_count": applied_count,
        "transition_counts": _transition_counts(changes),
        "changes": changes,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archetype",
        action="append",
        required=True,
        choices=CANONICAL_LANE_SLUGS,
        help="Canonical lane to target; repeat for multiple lanes.",
    )
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--apply", action="store_true", help="Persist reported changes.")
    parser.add_argument(
        "--config-json",
        type=Path,
        help="Full scrape-configuration document for pre-migration dry-runs only.",
    )
    parser.add_argument("--page-size", type=_positive_int, default=1000)
    parser.add_argument("--write-chunk-size", type=_positive_int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply and args.config_json is not None:
        parser.error("--config-json cannot be combined with --apply")
    try:
        report = run_backfill(
            _get_db(),
            archetypes=args.archetype,
            expected_revision=args.expected_revision,
            apply=args.apply,
            config_json=args.config_json,
            page_size=args.page_size,
            write_chunk_size=args.write_chunk_size,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
