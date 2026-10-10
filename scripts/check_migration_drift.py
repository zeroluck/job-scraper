#!/usr/bin/env python3
"""Fail on migration drift in either direction.

Compares the recorded Supabase applied-history (manifest `applied`, last synced
from `supabase_list_migrations` / `supabase_migrations.schema_migrations`)
against the authoritative repo file set:

  direction 1 (remote-applied-missing-locally): every applied migration name
    must be classified in the manifest as `owned` (points at repo file(s)) or
    `grandfathered` (legacy remote-only entry with a reason).
  direction 2 (local-missing-remotely): every migration file on disk
    (job-scraper supabase_setup/*.sql, job-scraper-web supabase/migrations/
    *.sql) must be referenced by `owned` or documented in `local_only`.

Also verifies manifest integrity: history_hash must equal
md5("version:name,..." over applied history sorted by version), so hand-edit
mistakes fail loudly instead of silently blessing a wrong baseline.

Rule (see README setup section): all DDL via repo migration files with
idempotent statements only (CREATE OR REPLACE, IF NOT EXISTS, guarded DO
blocks). Apply with `supabase db push` so stamps match, or MCP apply +
immediate manifest update using the RETURNED stamp (`--update-hash` refreshes
history_hash/last_verified after you append the new applied entry and its
owned mapping). CI has no live-database read path with current secrets, so it
enforces file<->manifest consistency; re-sync `applied` against live history
via MCP before trusting a green build after any out-of-band apply.

Usage:
  python scripts/check_migration_drift.py [--root R] [--web-root W] [--update-hash]
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

SETUP_DIRNAME = "supabase_setup"
WEB_MIGRATIONS = Path("supabase") / "migrations"
MANIFEST_NAME = "migration_manifest.json"


def canonical_history(applied):
    ordered = sorted(applied, key=lambda e: e["version"])
    return ",".join(f'{e["version"]}:{e["name"]}' for e in ordered)


def history_hash(applied):
    return hashlib.md5(canonical_history(applied).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="job-scraper repo root")
    ap.add_argument("--web-root", default=None, help="job-scraper-web repo root")
    ap.add_argument("--update-hash", action="store_true",
                    help="recompute history_hash/last_verified (only when validation passes)")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[1]
    manifest_path = root / SETUP_DIRNAME / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    errors: list[str] = []
    warnings: list[str] = []

    # 0. Integrity: hash must match the recorded applied history.
    if manifest.get("history_hash") != history_hash(manifest["applied"]):
        errors.append(
            f"history_hash mismatch in {manifest_path}: manifest was hand-edited "
            "without re-syncing. Re-run with --update-hash after fixing entries."
        )

    owned: dict = manifest.get("owned", {})
    grandfathered: dict = manifest.get("grandfathered", {})
    local_only: dict = manifest.get("local_only", {})

    # 1. Direction 1: every applied name must be classified.
    applied_names = [e["name"] for e in manifest["applied"]]
    for entry in manifest["applied"]:
        name = entry["name"]
        if name not in owned and name not in grandfathered:
            errors.append(
                f"remote-applied-missing-locally: {entry['version']} {name} "
                "has no owned/grandfathered manifest entry"
            )

    # Resolve web root (sibling checkout by default; CI passes it explicitly).
    web_root = Path(args.web_root) if args.web_root else root.parent / "job-scraper-web"
    if not web_root.is_dir():
        warnings.append(f"web checkout not found at {web_root}: skipping web file checks")
        web_root = None

    def resolve(ref: str) -> Path | None:
        repo, rel = ref.split(":", 1)
        if repo == "job-scraper":
            return root / rel
        if repo == "web":
            return web_root / rel if web_root else None
        errors.append(f"unknown repo tag in manifest ref: {ref}")
        return None

    # 2a. Direction 2a: every owned ref must exist on disk.
    referenced: set[str] = set()
    for name, spec in owned.items():
        for ref in spec["files"]:
            referenced.add(ref)
            p = resolve(ref)
            if p is None:
                continue  # web checkout absent; warned above
            if not p.is_file():
                errors.append(f"owned file missing on disk: {name} -> {ref}")

    # 2b. Direction 2b: every file on disk must be referenced or documented.
    on_disk: set[str] = set()
    setup_dir = root / SETUP_DIRNAME
    on_disk.update(f"job-scraper:{SETUP_DIRNAME}/{p.name}" for p in setup_dir.glob("*.sql"))
    if web_root:
        on_disk.update(f"web:{WEB_MIGRATIONS.as_posix()}/{p.name}" for p in (web_root / WEB_MIGRATIONS).glob("*.sql"))
    for ref in sorted(on_disk):
        if ref not in referenced and ref not in local_only:
            errors.append(f"local-missing-remotely: {ref} has no owned manifest entry")

    # 3. Advisory only: filename stamps vs applied versions (MCP applies
    # legitimately mint new stamps; same-name coverage is what must hold).
    for entry in manifest["applied"]:
        spec = owned.get(entry["name"])
        if not spec:
            continue
        for ref in spec["files"]:
            if ":supabase/migrations/" not in ref:
                continue
            stem = ref.rsplit("/", 1)[-1]
            if "_" in stem and not stem.split("_", 1)[0] == entry["version"]:
                warnings.append(
                    f"stamp differs (name coverage holds): {entry['version']} "
                    f"{entry['name']} <-> {stem}"
                )

    if errors:
        print("DRIFT CHECK FAILED")
        for e in errors:
            print(f"  FAIL: {e}")
        return 1

    if args.update_hash:
        manifest["history_hash"] = history_hash(manifest["applied"])
        manifest["last_verified"] = date.today().isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"drift check passed: {len(manifest['applied'])} applied entries, "
        f"{len(owned)} owned, {len(grandfathered)} grandfathered, "
        f"{len(local_only)} local-only, {len(warnings)} warnings"
    )
    for w in warnings:
        print(f"  warn: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
