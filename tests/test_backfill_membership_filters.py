import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import backfill_membership_filters as backfill
from lane_catalog import CANONICAL_LANE_SLUGS


def configuration_payload(revision=7):
    lanes = []
    for order, archetype in enumerate(CANONICAL_LANE_SLUGS):
        title_include = (
            [r"technical program manager"]
            if archetype == "technology_delivery"
            else [r"ai automation"]
            if archetype == "ai_workflow_automation"
            else [archetype]
        )
        lanes.append({
            "archetype": archetype,
            "display_name": archetype,
            "description": f"{archetype} roles",
            "routing_guidance": f"Route {archetype} roles.",
            "title_include": title_include,
            "title_exclude": [r"construction"],
            "description_include": [],
            "description_exclude": [],
            "enabled": True,
            "resume_profile_ready": True,
            "sort_order": order,
            "locations": ["canada"],
            "queries": [
                {
                    "archetype": archetype,
                    "query": f"{archetype} exact",
                    "query_type": "precision",
                    "language": "en",
                    "sort_order": 10,
                    "enabled": True,
                },
                {
                    "archetype": archetype,
                    "query": f"{archetype} broad",
                    "query_type": "recall",
                    "language": "en",
                    "sort_order": 20,
                    "enabled": True,
                },
            ],
        })
    return {
        "version": 1,
        "revision": revision,
        "aliases": {"software_tpm": "technology_delivery"},
        "settings": {
            "scraping_enabled": True,
            "lookback_days": 3,
            "max_jobs_per_query": 25,
            "max_pages_per_query": 4,
            "request_delay_ms": 750,
            "concurrent_queries": 3,
            "deduplicate_jobs": True,
            "fetch_descriptions": True,
            "score_jobs": False,
            "options": {},
            "updated_at": "2026-09-01T00:00:00+00:00",
        },
        "lanes": lanes,
    }


def membership(job_id, lane, status="pending", is_filtered=False, reason=None):
    return {
        "job_id": job_id,
        "archetype": lane,
        "filter_status": status,
        "is_filtered": is_filtered,
        "filter_reason": reason,
    }


class FakeQuery:
    def __init__(self, db):
        self.db = db
        self.filters = []
        self.range_value = None
        self.update_payload = None

    def select(self, fields):
        self.db.selects.append(fields)
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, list(values)))
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def is_(self, field, value):
        assert value == "null"
        self.filters.append(("is_null", field, None))
        return self

    def order(self, field):
        self.db.orders.append(field)
        return self

    def range(self, start, end):
        self.range_value = (start, end)
        self.db.ranges.append(self.range_value)
        return self

    def update(self, payload):
        self.update_payload = dict(payload)
        return self

    def _matches(self, row):
        for operator, field, value in self.filters:
            if operator == "in" and row.get(field) not in value:
                return False
            if operator == "eq" and row.get(field) != value:
                return False
            if operator == "is_null" and row.get(field) is not None:
                return False
        return True

    def execute(self):
        if self.update_payload is not None:
            updated = []
            for row in self.db.memberships:
                if self._matches(row):
                    row.update(self.update_payload)
                    updated.append(copy.deepcopy(row))
            self.db.updates.append((self.update_payload, list(self.filters)))
            return SimpleNamespace(data=updated)

        rows = []
        for row in self.db.memberships:
            if self._matches(row):
                result = copy.deepcopy(row)
                result["jobs"] = copy.deepcopy(self.db.jobs[row["job_id"]])
                rows.append(result)
        rows.sort(key=lambda row: (row["archetype"], row["job_id"]))
        if self.range_value is not None:
            start, end = self.range_value
            rows = rows[start:end + 1]
        return SimpleNamespace(data=rows)


class FakeDB:
    def __init__(self, memberships, jobs, revision=7):
        self.memberships = copy.deepcopy(memberships)
        self.jobs = copy.deepcopy(jobs)
        self.configuration = configuration_payload(revision)
        self.rpc_calls = 0
        self.selects = []
        self.orders = []
        self.ranges = []
        self.updates = []

    def rpc(self, name):
        assert name == "get_scraper_configuration"
        self.rpc_calls += 1
        payload = copy.deepcopy(self.configuration)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=payload))

    def table(self, name):
        assert name == "job_archetype_memberships"
        return FakeQuery(self)


def jobs():
    return {
        "job-1": {
            "job_id": "job-1",
            "job_title": "Senior Technical Program Manager",
            "company": "Example Corp",
            "description": "Own delivery.",
        },
        "job-2": {
            "job_id": "job-2",
            "job_title": "AI Automation Lead",
            "company": "Example Corp",
            "description": "Automate workflows.",
        },
    }


def test_dry_run_reports_every_change_without_writes():
    db = FakeDB(
        [membership("job-1", "technology_delivery", "filtered", True, "stale")],
        jobs(),
    )

    report = backfill.run_backfill(
        db, archetypes=["technology_delivery"], expected_revision=7, page_size=1
    )

    assert report["mode"] == "dry-run"
    assert report["change_count"] == 1
    assert report["transition_counts"] == {"filtered->included": 1}
    assert report["changes"] == [{
        "job_id": "job-1",
        "lane": "technology_delivery",
        "title": "Senior Technical Program Manager",
        "old_status": "filtered",
        "new_status": "included",
        "old_is_filtered": True,
        "new_is_filtered": False,
        "old_reason": "stale",
        "new_reason": None,
    }]
    assert db.updates == []
    assert db.ranges == [(0, 0), (1, 1)]
    assert backfill.MEMBERSHIP_SELECT in db.selects


def test_apply_updates_only_membership_filter_fields():
    db = FakeDB([membership("job-1", "technology_delivery")], jobs())

    report = backfill.run_backfill(
        db,
        archetypes=["technology_delivery"],
        expected_revision=7,
        apply=True,
        write_chunk_size=1,
    )

    assert report["applied_count"] == 1
    assert db.memberships[0]["filter_status"] == "included"
    assert db.updates[0][0] == {
        "filter_status": "included",
        "is_filtered": False,
        "filter_reason": None,
    }
    assert ("eq", "archetype", "technology_delivery") in db.updates[0][1]


def test_revision_mismatch_stops_before_membership_read_or_write():
    db = FakeDB([membership("job-1", "technology_delivery")], jobs(), revision=8)

    with pytest.raises(backfill.ConfigurationRevisionMismatch, match="expected 7, got 8"):
        backfill.run_backfill(
            db,
            archetypes=["technology_delivery"],
            expected_revision=7,
            apply=True,
        )

    assert db.selects == []
    assert db.updates == []


def test_lane_scope_never_reads_or_modifies_other_lanes():
    db = FakeDB(
        [
            membership("job-1", "technology_delivery"),
            membership("job-2", "ai_workflow_automation"),
        ],
        jobs(),
    )

    report = backfill.run_backfill(
        db,
        archetypes=["technology_delivery"],
        expected_revision=7,
        apply=True,
    )

    assert report["memberships_scanned"] == 1
    assert db.memberships[1]["filter_status"] == "pending"
    read_filters = db.updates[0][1]
    assert ("eq", "archetype", "technology_delivery") in read_filters


def test_second_dry_run_is_idempotent():
    db = FakeDB([membership("job-1", "technology_delivery")], jobs())
    backfill.run_backfill(
        db,
        archetypes=["technology_delivery"],
        expected_revision=7,
        apply=True,
    )

    report = backfill.run_backfill(
        db, archetypes=["technology_delivery"], expected_revision=7
    )

    assert report["change_count"] == 0
    assert report["changes"] == []
    assert report["transition_counts"] == {}


def test_full_document_file_override_is_dry_run_only(tmp_path: Path):
    path = tmp_path / "scrape-configuration.json"
    path.write_text(json.dumps(configuration_payload()), encoding="utf-8")
    db = FakeDB([membership("job-1", "technology_delivery")], jobs())

    report = backfill.run_backfill(
        db,
        archetypes=["technology_delivery"],
        expected_revision=7,
        config_json=path,
    )

    assert report["change_count"] == 1
    assert db.rpc_calls == 0
    with pytest.raises(ValueError, match="restricted to dry-runs"):
        backfill.run_backfill(
            db,
            archetypes=["technology_delivery"],
            expected_revision=7,
            apply=True,
            config_json=path,
        )
