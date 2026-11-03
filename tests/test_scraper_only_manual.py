"""Offline guard and manual workflow contract checks."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
import linkedin_discovery as discovery


def test_guard_rejects_missing_cycle_before_any_work(monkeypatch):
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", "7")
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", "9")
    with pytest.raises(discovery.DiscoveryError, match="sealed cycle identity"):
        discovery.require_detail_only_cycle(None, {"detail": 300}, partial=False)


class PendingRead:
    def __init__(self, count):
        self.count = count
        self.calls = []

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def select(self, *args, **kwargs):
        self.calls.append(("select", args, kwargs))
        return self

    def eq(self, *args):
        self.calls.append(("eq", args))
        return self

    def execute(self):
        return SimpleNamespace(count=self.count)


@pytest.mark.parametrize("cycle,limit,partial,count,error", [
    ({"cycle_id": 8, "discovery_sequence": 9, "search_status": "sealed"}, 300, False, 927, "identity"),
    ({"cycle_id": 7, "discovery_sequence": 10, "search_status": "sealed"}, 300, False, 927, "identity"),
    ({"cycle_id": 7, "discovery_sequence": 9, "search_status": "running"}, 300, False, 927, "identity"),
    ({"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"}, 301, False, 927, "300-task"),
    ({"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"}, 300, True, 927, "identity"),
    ({"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"}, 300, False, 0, "pending"),
    ({"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"}, 300, False, None, "pending"),
])
def test_guard_fail_closed(monkeypatch, cycle, limit, partial, count, error):
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", "7")
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", "9")
    db = PendingRead(count)
    monkeypatch.setattr(discovery.supabase_utils, "supabase", db)
    with pytest.raises(discovery.DiscoveryError, match=error):
        discovery.require_detail_only_cycle(cycle, {"detail": limit}, partial=partial)
    if error != "pending":
        assert db.calls == []


def test_guard_accepts_exact_identity_and_pending_read_only(monkeypatch):
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", "7")
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", "9")
    db = PendingRead(927)
    monkeypatch.setattr(discovery.supabase_utils, "supabase", db)
    discovery.require_detail_only_cycle(
        {"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"},
        {"detail": 300}, partial=False,
    )
    assert db.calls == [
        ("table", "linkedin_discovery_tasks"),
        ("select", ("id",), {"count": "exact", "head": True}),
        ("eq", ("status", "pending")),
    ]


def test_real_discovery_guard_stops_before_new_cycle(monkeypatch):
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", "7")
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", "9")
    monkeypatch.setattr(discovery.supabase_utils, "get_resumable_linkedin_discovery_cycle", lambda **kw: None)
    def forbidden(*args, **kwargs):
        pytest.fail("guard allowed creation, source request or claim")
    for name in ("create_linkedin_discovery_cycle", "claim_linkedin_discovery_tasks"):
        monkeypatch.setattr(discovery.supabase_utils, name, forbidden)
    monkeypatch.setattr(discovery, "_scope_manifest", forbidden)
    monkeypatch.setattr(discovery, "_request_page", forbidden)
    configuration = SimpleNamespace(settings=SimpleNamespace(
        options={"max_detail_tasks_per_run": 300}, max_pages_per_query=3, max_jobs_per_query=50))
    with pytest.raises(discovery.DiscoveryError, match="identity"):
        discovery.run_discovery(configuration, [], parse_cards=forbidden,
            detail_fetch=forbidden, save_details=forbidden, partial=False)


@pytest.mark.parametrize("cycle_id,sequence", [("", "9"), ("7", ""), ("0", "9"), ("7", "9x"), ("７", "9")])
def test_identity_inputs_are_strict_positive_decimal(monkeypatch, cycle_id, sequence):
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", cycle_id)
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", sequence)
    with pytest.raises(discovery.DiscoveryError, match="identity"):
        discovery.require_detail_only_cycle(
            {"cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"},
            {"detail": 300}, partial=False,
        )


def test_preflight_uses_same_guard_and_db_configuration(monkeypatch):
    import scripts.preflight_scraper_only as preflight
    for name, value in {"LINKEDIN_DISCOVERY_MODE": "adaptive_queue", "SCRAPE_CONFIG_SOURCE": "db",
                        "SCRAPE_ARCHETYPE": "", "LINKEDIN_DETAIL_ONLY_CYCLE_ID": "7",
                        "LINKEDIN_DETAIL_ONLY_SEQUENCE": "9"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(preflight.config, "SCRAPING_SOURCES", ["linkedin"])
    db = PendingRead(927)
    monkeypatch.setattr(preflight.supabase_utils, "supabase", db)
    monkeypatch.setattr(preflight, "load_scrape_configuration", lambda **kw: SimpleNamespace(
        settings=SimpleNamespace(options={"max_detail_tasks_per_run": 300}, max_pages_per_query=3, max_jobs_per_query=50)))
    monkeypatch.setattr(preflight.supabase_utils, "get_resumable_linkedin_discovery_cycle", lambda **kw: {
        "cycle_id": 7, "discovery_sequence": 9, "search_status": "sealed"})
    preflight.main()
    assert db.calls[-1] == ("eq", ("status", "pending"))
    monkeypatch.setenv("SCRAPE_ARCHETYPE", "unexpected")
    with pytest.raises(SystemExit, match="environment"):
        preflight.main()


def test_guard_is_noop_for_existing_workflows(monkeypatch):
    monkeypatch.delenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", raising=False)
    monkeypatch.delenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", raising=False)
    discovery.require_detail_only_cycle(None, {}, partial=True)


def test_manual_workflow_is_manual_serialized_scraper_only():
    root = Path(__file__).resolve().parents[1]
    path = root / ".github/workflows/scraper_only_manual.yml"
    assert path.exists(), "manual-only workflow missing"
    workflow = yaml.safe_load(path.read_text())
    original = yaml.safe_load((root / ".github/workflows/scrape_jobs.yml").read_text())
    # PyYAML treats YAML 1.1 'on' as boolean; GitHub uses YAML 1.2.
    assert set(workflow.get("on", workflow.get(True))) == {"workflow_dispatch"}
    assert workflow["concurrency"] == original["concurrency"]
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["jobs"]) == {"scrape"}
    job = workflow["jobs"]["scrape"]
    assert job["env"] == original["jobs"]["scrape"]["env"]
    steps = job["steps"]
    assert any(s.get("uses") == "./.github/actions/configure-data-api" for s in steps)
    assert steps[-1]["run"] == "python scraper.py"
    assert steps[-1]["env"]["SCRAPE_CONFIG_SOURCE"] == "db"
    assert steps[-1]["env"]["SCRAPE_ARCHETYPE"] == ""
    text = path.read_text()
    for forbidden in ("incremental_freehire", "backfill_freehire", "publication_gate", "gate_watchdog", "reset_linkedin", "LLM_API_KEY", "OPENAI_API_KEY", "schedule:"):
        assert forbidden not in text
    assert any("preflight_scraper_only.py" in s.get("run", "") for s in steps)
