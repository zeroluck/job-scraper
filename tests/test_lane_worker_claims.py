import sys
from types import SimpleNamespace

import pytest

try:
    import bs4  # noqa: F401
except ModuleNotFoundError:
    sys.modules.setdefault("freehire_compat", SimpleNamespace())

import supabase_utils


class RpcDb:
    def __init__(self, result=True):
        self.calls = []
        self.result = result

    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.result))


def test_scoring_and_resume_fetches_pass_worker_identity_and_separate_rpcs(monkeypatch):
    db = RpcDb(result=[{"job_id": "job-1"}])
    monkeypatch.setattr(supabase_utils, "supabase", db)

    assert supabase_utils.get_jobs_to_score(2, "data_pm", "score-worker", 45)
    assert supabase_utils.get_jobs_to_rescore(2, "data_pm", "rescore-worker", 50)
    assert supabase_utils.get_top_scored_jobs_for_resume_generation(3, "data_pm", "resume-worker", 60)
    assert db.calls == [
        ("get_lane_jobs_to_score", {"p_archetype": "data_pm", "p_limit": 2, "p_worker_id": "score-worker", "p_lease_seconds": 45}),
        ("get_lane_jobs_for_rescore", {"p_archetype": "data_pm", "p_limit": 2, "p_worker_id": "rescore-worker", "p_lease_seconds": 50}),
        ("get_lane_jobs_for_resume_generation", {"p_archetype": "data_pm", "p_limit": 3, "p_worker_id": "resume-worker", "p_lease_seconds": 60}),
    ]


def test_success_and_failure_claim_transitions_are_owner_protected_rpcs(monkeypatch):
    db = RpcDb()
    monkeypatch.setattr(supabase_utils, "supabase", db)

    assert supabase_utils.update_job_score("job-1", 88, "initial", "data_pm", "score-worker")
    assert supabase_utils.release_lane_score_claim("job-2", "data_pm", "score-worker", failed=True)
    assert supabase_utils.complete_lane_resume_claim("job-3", "data_pm", "resume-worker", "resume-id", "base-id")
    assert supabase_utils.release_lane_resume_claim("job-4", "data_pm", "resume-worker", failed=True)
    assert [name for name, _ in db.calls] == [
        "complete_lane_score_claim", "fail_lane_score_claim",
        "complete_lane_resume_claim", "fail_lane_resume_claim",
    ]
    assert all(args["p_worker_id"].endswith("worker") for _, args in db.calls)


def test_score_completion_retries_transient_statement_timeout(monkeypatch):
    class TimeoutThenSuccess(RpcDb):
        def rpc(self, name, args):
            self.calls.append((name, args))

            def execute():
                if len(self.calls) == 1:
                    raise RuntimeError("57014 canceling statement due to statement timeout")
                return SimpleNamespace(data=True)

            return SimpleNamespace(execute=execute)

    db = TimeoutThenSuccess()
    monkeypatch.setattr(supabase_utils, "supabase", db)
    monkeypatch.setattr(supabase_utils.time, "sleep", lambda _seconds: None)

    assert supabase_utils.update_job_score(
        "job-1", 88, "initial", "data_pm", "score-worker"
    )
    assert [name for name, _args in db.calls] == [
        "complete_lane_score_claim",
        "complete_lane_score_claim",
    ]


def test_lane_claim_database_errors_fail_the_worker(monkeypatch):
    class FailingDb:
        def rpc(self, _name, _args):
            return SimpleNamespace(
                execute=lambda: (_ for _ in ()).throw(RuntimeError("database unavailable"))
            )

    monkeypatch.setattr(supabase_utils, "supabase", FailingDb())

    with pytest.raises(RuntimeError, match="database unavailable"):
        supabase_utils.get_jobs_to_score(1, "data_pm", "score-worker")
    with pytest.raises(RuntimeError, match="database unavailable"):
        supabase_utils.get_jobs_to_rescore(1, "data_pm", "score-worker")
