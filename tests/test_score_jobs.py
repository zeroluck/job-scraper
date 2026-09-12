import importlib
import json
import sys
from types import SimpleNamespace

import supabase_utils


def test_get_resume_score_uses_job_scoring_client_without_reasoning(monkeypatch):
    fake_supabase_utils = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "supabase_utils", fake_supabase_utils)
    score_jobs = importlib.import_module("score_jobs")

    calls = []

    class FakeClient:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return "87"

    monkeypatch.setattr(score_jobs, "job_scoring_client", FakeClient(), raising=False)

    result = score_jobs.get_resume_score_from_ai(
        "Resume text",
        {
            "job_id": "job-1",
            "company": "Acme",
            "job_title": "Technical Project Manager",
            "description": "Lead technical delivery.",
            "level": "Senior",
        },
    )

    assert result == 87
    assert calls[0]["reasoning_effort"] == "low"
    assert "temperature" not in calls[0]
    assert calls[0]["max_tokens"] == 16


def test_batch_scoring_returns_only_requested_valid_jobs(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")

    class FakeClient:
        def generate_content(self, **kwargs):
            assert kwargs["response_format"] is score_jobs.JobScoreResultList
            assert kwargs["max_tokens"] == 1000
            return json.dumps({"jobs": [
                {"job_id": "job-1", "score": 87},
                {"job_id": "unknown", "score": 10},
            ]})

    monkeypatch.setattr(score_jobs, "job_scoring_client", FakeClient())

    assert score_jobs.get_resume_scores_from_ai("resume", [{
        "job_id": "job-1",
        "description": "Lead delivery",
    }]) == {"job-1": 87}


def test_batch_scoring_rejects_invalid_or_malformed_output(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")

    class FakeClient:
        def generate_content(self, **_kwargs):
            return '{"jobs":[{"job_id":"job-1","score":101}]}'

    monkeypatch.setattr(score_jobs, "job_scoring_client", FakeClient())
    monkeypatch.setattr(score_jobs, "get_resume_score_from_ai", lambda *_args: None)

    assert score_jobs.get_resume_scores_from_ai("resume", [{
        "job_id": "job-1",
        "description": "Lead delivery",
    }]) == {}


def test_batch_scoring_preserves_valid_items_and_recovers_missing(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    calls = []

    class FakeClient:
        def generate_content(self, **_kwargs):
            calls.append("batch")
            return json.dumps({"jobs": [
                {"job_id": "job-1", "score": 87},
                {"job_id": "job-2", "score": 101},
            ]})

    monkeypatch.setattr(score_jobs, "job_scoring_client", FakeClient())
    monkeypatch.setattr(
        score_jobs,
        "get_resume_score_from_ai",
        lambda _resume, job: 65 if job["job_id"] == "job-2" else None,
    )

    result = score_jobs.get_resume_scores_from_ai("resume", [
        {"job_id": "job-1", "description": "One"},
        {"job_id": "job-2", "description": "Two"},
    ])

    assert result == {"job-1": 87, "job-2": 65}
    assert calls == ["batch", "batch"]


def test_batch_fallback_bounds_description(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    fallback_lengths = []

    class FakeClient:
        def generate_content(self, **_kwargs):
            return '{"jobs":[]}'

    monkeypatch.setattr(score_jobs, "job_scoring_client", FakeClient())
    monkeypatch.setattr(score_jobs.config, "JOB_SCORE_DESCRIPTION_MAX_CHARS", 10)
    monkeypatch.setattr(
        score_jobs,
        "get_resume_score_from_ai",
        lambda _resume, job: fallback_lengths.append(len(job["description"])) or 50,
    )

    result = score_jobs.get_resume_scores_from_ai("resume", [{
        "job_id": "job-1",
        "description": "x" * 100,
    }])

    assert result == {"job-1": 50}
    assert fallback_lengths == [10]


def test_main_batches_initial_scoring_and_completes_each_claim(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    monkeypatch.setattr(score_jobs, "supabase_utils", supabase_utils)
    jobs = [
        {"job_id": "job-1", "description": "One"},
        {"job_id": "job-2", "description": "Two"},
    ]
    updates = []
    releases = []
    monkeypatch.setattr(score_jobs.supabase_utils, "get_archetype_base_resume", lambda _lane: {"name": "Jane", "base_resume_id": "base"})
    monkeypatch.setattr(score_jobs.supabase_utils, "get_jobs_to_score", lambda *_args, **_kwargs: jobs)
    monkeypatch.setattr(score_jobs.supabase_utils, "update_job_score", lambda job_id, score, **kwargs: updates.append((job_id, score, kwargs)) or True)
    monkeypatch.setattr(score_jobs.supabase_utils, "release_lane_score_claim", lambda *args, **kwargs: releases.append((args, kwargs)) or True)
    batches = []
    monkeypatch.setattr(score_jobs.config, "JOB_SCORE_BATCH_SIZE", 1)
    monkeypatch.setattr(score_jobs, "get_resume_scores_from_ai", lambda _resume, batch: batches.append([job["job_id"] for job in batch]) or {job["job_id"]: 80 for job in batch})
    monkeypatch.setattr(score_jobs, "rescore_jobs_with_custom_resume", lambda **_kwargs: {"claimed": 0, "scored": 0, "failed": 0})

    result = score_jobs.main("technology_delivery", run_filter_prepass=False, worker_id="worker")

    assert [(job_id, score) for job_id, score, _kwargs in updates] == [("job-1", 80), ("job-2", 80)]
    assert result["initial_claimed"] == 2
    assert result["initial_scored"] == 2
    assert batches == [["job-1"], ["job-2"]]
    assert releases == []


def test_main_releases_omitted_score_claim_once(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    monkeypatch.setattr(score_jobs, "supabase_utils", supabase_utils)
    releases = []
    monkeypatch.setattr(score_jobs.supabase_utils, "get_archetype_base_resume", lambda _lane: {"name": "Jane", "base_resume_id": "base"})
    monkeypatch.setattr(score_jobs.supabase_utils, "get_jobs_to_score", lambda *_args, **_kwargs: [{"job_id": "job-1", "description": "One"}])
    monkeypatch.setattr(score_jobs, "get_resume_scores_from_ai", lambda *_args: {})
    monkeypatch.setattr(score_jobs.supabase_utils, "release_lane_score_claim", lambda *args, **kwargs: releases.append((args, kwargs)) or True)
    monkeypatch.setattr(score_jobs, "rescore_jobs_with_custom_resume", lambda **_kwargs: {"claimed": 0, "scored": 0, "failed": 0})

    result = score_jobs.main("technology_delivery", run_filter_prepass=False, worker_id="worker")

    assert result["initial_failed"] == 1
    assert releases == [(('job-1', 'technology_delivery', 'worker'), {"failed": True})]


def test_scheduled_scoring_skips_successfully_when_db_setting_is_false(monkeypatch):
    import scheduled_scoring
    configuration = SimpleNamespace(settings=SimpleNamespace(score_jobs=False))
    monkeypatch.setattr(scheduled_scoring, "load_scrape_configuration", lambda db: configuration)

    worker = lambda _lane: (_ for _ in ()).throw(AssertionError("must not score"))
    assert scheduled_scoring.run_configured_scoring(worker, db=object()) == {
        "status": "skipped_score_jobs_disabled"
    }


def test_scheduled_scoring_loads_db_setting_before_lane_orchestration(monkeypatch):
    import scheduled_scoring
    calls = []
    configuration = SimpleNamespace(settings=SimpleNamespace(score_jobs=True))
    monkeypatch.setattr(
        scheduled_scoring,
        "load_scrape_configuration",
        lambda db: calls.append(("load", db)) or configuration,
    )
    monkeypatch.setattr(
        scheduled_scoring,
        "run_enabled_lanes",
        lambda worker, **kwargs: calls.append(("run", kwargs)) or {"ok": True},
    )
    db = object()

    assert scheduled_scoring.run_configured_scoring(
        lambda _lane: None,
        db=db, archetype_override="network_infrastructure"
    ) == {"ok": True}
    assert calls == [
        ("load", db),
        ("run", {"db": db, "override": "network_infrastructure"}),
    ]


def test_backlog_drain_stops_when_a_pass_claims_no_work(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    calls = []
    results = iter([
        {"lane": {
            "initial_claimed": 1,
            "initial_scored": 1,
            "rescore_claimed": 0,
            "rescore_scored": 0,
        }},
        {"lane": {
            "initial_claimed": 0,
            "initial_scored": 0,
            "rescore_claimed": 0,
            "rescore_scored": 0,
        }},
    ])
    monkeypatch.setattr(
        score_jobs,
        "run_configured_scoring",
        lambda *_args, **_kwargs: calls.append("pass") or next(results),
    )
    monkeypatch.setattr(score_jobs.time, "monotonic", lambda: 0)

    result = score_jobs.run_scheduled_scoring(
        db=object(), drain_backlog=True
    )

    assert calls == ["pass", "pass"]
    assert result["status"] == "completed"
    assert len(result["passes"]) == 2


def test_backlog_drain_stops_after_zero_progress(monkeypatch):
    score_jobs = importlib.import_module("score_jobs")
    calls = []
    monkeypatch.setattr(
        score_jobs,
        "run_configured_scoring",
        lambda *_args, **_kwargs: calls.append("pass") or {"lane": {
            "initial_claimed": 2,
            "initial_scored": 0,
            "rescore_claimed": 0,
            "rescore_scored": 0,
        }},
    )
    monkeypatch.setattr(score_jobs.time, "monotonic", lambda: 0)

    score_jobs.run_scheduled_scoring(db=object(), drain_backlog=True)

    assert calls == ["pass"]


def test_get_top_scored_jobs_to_apply_excludes_filtered_jobs(monkeypatch):
    class FakeQuery:
        def __init__(self):
            self.calls = []

        def select(self, value):
            self.calls.append(("select", value))
            return self

        def eq(self, key, value):
            self.calls.append(("eq", key, value))
            return self

        @property
        def not_(self):
            self.calls.append(("not_",))
            return self

        def is_(self, key, value):
            self.calls.append(("is_", key, value))
            return self

        def order(self, key, desc=False):
            self.calls.append(("order", key, desc))
            return self

        def limit(self, value):
            self.calls.append(("limit", value))
            return self

        def execute(self):
            self.calls.append(("execute",))
            return SimpleNamespace(data=[{"job_id": "job-1", "resume_score": 92}])

    class FakeDb:
        def __init__(self):
            self.query = FakeQuery()

        def table(self, name):
            assert name == supabase_utils.config.SUPABASE_TABLE_NAME
            return self.query

    db = FakeDb()
    monkeypatch.setattr(supabase_utils, "supabase", db)

    result = supabase_utils.get_top_scored_jobs_to_apply(10)

    assert result == [{"job_id": "job-1", "resume_score": 92}]
    assert ("eq", "is_active", True) in db.query.calls
    assert ("eq", "status", "new") in db.query.calls
    assert ("eq", "is_filtered", False) in db.query.calls
    assert ("not_",) in db.query.calls
    assert ("is_", "resume_score", None) in db.query.calls
    assert ("order", "resume_score", True) in db.query.calls
    assert ("limit", 10) in db.query.calls


def test_update_job_score_isolated_to_membership_lane(monkeypatch):
    calls = []
    class Query:
        def update(self, payload): calls.append(("update", payload)); return self
        def eq(self, key, value): calls.append(("eq", key, value)); return self
        def execute(self): return SimpleNamespace(data=[{}])
    class Db:
        def table(self, name): calls.append(("table", name)); return Query()
    monkeypatch.setattr(supabase_utils, "supabase", Db())

    assert supabase_utils.update_job_score("job-1", 88, archetype="data_pm") is True
    assert ("table", "job_archetype_memberships") in calls
    assert ("eq", "job_id", "job-1") in calls
    assert ("eq", "archetype", "data_pm") in calls
    assert not any(call == ("table", supabase_utils.config.SUPABASE_TABLE_NAME) for call in calls)


def test_scores_for_same_job_do_not_overwrite_another_lane(monkeypatch):
    scores = {}
    class Query:
        def __init__(self): self.payload = None; self.job = None; self.lane = None
        def update(self, payload): self.payload = payload; return self
        def eq(self, key, value):
            if key == "job_id": self.job = value
            if key == "archetype": self.lane = value
            return self
        def execute(self): scores[(self.job, self.lane)] = self.payload["match_score"]; return SimpleNamespace(data=[{}])
    class Db:
        def table(self, name): assert name == "job_archetype_memberships"; return Query()
    monkeypatch.setattr(supabase_utils, "supabase", Db())
    supabase_utils.update_job_score("job-1", 91, archetype="data_pm")
    supabase_utils.update_job_score("job-1", 64, archetype="network_infrastructure")
    assert scores == {("job-1", "data_pm"): 91, ("job-1", "network_infrastructure"): 64}
