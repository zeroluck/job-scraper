"""Offline physical-attempt checks using the real wrapper and classifier."""
import json
import re
from types import SimpleNamespace

import pytest
import backfill_freehire_compat
import config
import freehire_compat
import llm_client


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=content))])


def client(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(config, "FREEHIRE_CLASSIFY_RETRY_BASE_SECONDS", 0)
    return llm_client.LLMClient(
        model="gemini/test-a", model_chain=["gemini/test-a", "gemini/test-b"],
        max_rpm=10000, request_delay=0, max_retries=3)


def test_failed_completion_and_fallback_share_one_physical_cap(monkeypatch):
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("503 service unavailable")
        return response('{"jobs":[]}')

    monkeypatch.setattr(llm_client.litellm, "completion", completion)
    outcome = freehire_compat.classify_batch(
        [{"job_id": "1"}], client=client(monkeypatch), max_requests=1,
        sleep_fn=lambda _: None)
    assert len(calls) == outcome.requests == 1
    assert outcome.failures == {}  # Exhaustion is not a durable classification failure.


@pytest.mark.parametrize("drain,page_limit", [(False, 4), (True, 1)])
def test_invocation_cap_spans_batches_and_drained_pages(monkeypatch, drain, page_limit):
    from test_backfill_freehire_compat import Db

    rows = [{"job_id": str(i), "provider": "linkedin", "description": "APIs",
             "freehire_compat_status": "pending"} for i in range(4)]
    db = Db(rows)
    untouched = [dict(row) for row in rows[2:]]
    monkeypatch.setattr(backfill_freehire_compat, "fetch_incremental_candidates",
                        lambda db, limit: [dict(row) for row in db.rows
                                           if row["freehire_compat_status"] == "pending"][:limit])
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        ids = re.findall(r"Job ID: (\S+)", kwargs["messages"][-1]["content"])
        return response(json.dumps({"jobs": [
            {"job_id": job_id, "category": "backend", "seniority": "", "confidence": .9}
            for job_id in ids]}))

    monkeypatch.setattr(llm_client.litellm, "completion", completion)
    monkeypatch.setattr(config, "FREEHIRE_CLASSIFY_REQUEST_BUDGET", 2)
    monkeypatch.setattr(freehire_compat, "pack_batches", lambda jobs, **_: [[j] for j in jobs])
    result = backfill_freehire_compat.run(
        apply=True, drain_backlog=drain, limit=page_limit, db=db, client=client(monkeypatch))
    assert len(calls) == result["llm_requests"] == 2
    assert result["classified"] == 2
    assert db.rpc_names.count("claim_freehire_compat_jobs") == 2
    assert rows[2:] == untouched


def test_nested_retries_are_explicitly_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_client.litellm, "completion",
                        lambda **kw: calls.append(kw) or response('{"jobs":[]}'))
    client(monkeypatch).generate_content("test", max_api_attempts=1)
    assert calls[0]["num_retries"] == calls[0]["max_retries"] == 0


def test_malformed_json_is_counted_once(monkeypatch):
    class MalformedClient:
        model = "test/model"
        model_chain = None

        def generate_content(self, **kwargs):
            if kwargs.get("request_budget") is not None:
                kwargs["request_budget"].consume()
            return "not JSON"

    outcome = freehire_compat.classify_batch(
        [{"job_id": "1"}], client=MalformedClient(), max_requests=1,
        sleep_fn=lambda _: None)
    assert outcome.requests == 1
    assert outcome.failures == {}


@pytest.mark.parametrize("cap", [0, 1, 2, 3, 5])
def test_recursive_split_tree_never_exceeds_physical_cap(monkeypatch, cap):
    calls = []
    monkeypatch.setattr(llm_client.litellm, "completion",
                        lambda **kw: calls.append(kw) or response('{"jobs":[]}'))
    outcome = freehire_compat.classify_batch(
        [{"job_id": str(i)} for i in range(8)], client=client(monkeypatch),
        max_requests=cap, max_retries=1, sleep_fn=lambda _: None)
    assert len(calls) == outcome.requests == cap
    assert set(outcome.failures) <= {"0"}  # A leaf can fail before the budget runs out.
    if cap > 1:
        assert outcome.splits > 0


@pytest.mark.parametrize("raw", ["not JSON", '{"jobs":[]}', '{"jobs":[{"job_id":"0","category":"backend","seniority":"","confidence":0.9}]}'])
def test_exhausted_batch_keeps_unfinished_claims_and_other_leases(monkeypatch, raw):
    from test_backfill_freehire_compat import Db

    rows = [{"job_id": str(i), "provider": "linkedin", "description": "APIs",
             "freehire_compat_status": "pending"} for i in range(3)]
    rows.append({"job_id": "leased", "provider": "linkedin", "description": "APIs",
                 "freehire_compat_status": "processing", "freehire_compat_claimed_by": "other",
                 "freehire_compat_claimed_at": "2999-01-01T00:00:00+00:00"})
    db = Db(rows)
    lease_before = dict(rows[-1])
    calls = []
    monkeypatch.setattr(config, "FREEHIRE_CLASSIFY_REQUEST_BUDGET", 1)
    monkeypatch.setattr(freehire_compat, "pack_batches", lambda jobs, **_: [jobs[:2], jobs[2:]])
    monkeypatch.setattr(llm_client.litellm, "completion",
                        lambda **kw: calls.append(kw) or response(raw))
    result = backfill_freehire_compat.run(apply=True, limit=4, db=db, client=client(monkeypatch))
    assert len(calls) == result["llm_requests"] == 1
    assert result["failed"] == 0
    assert rows[1]["freehire_compat_status"] == "processing"
    assert rows[1]["freehire_compat_claimed_by"]
    assert not rows[1].get("freehire_compat_next_retry_at")
    assert rows[2]["freehire_compat_status"] == "pending"
    assert rows[-1] == lease_before


def test_zero_invocation_budget_does_not_claim(monkeypatch):
    from test_backfill_freehire_compat import Db
    from llm_budget import RequestBudget

    row = {"job_id": "1", "provider": "linkedin", "description": "APIs",
           "freehire_compat_status": "pending"}
    db = Db([row])
    before = dict(row)
    result = backfill_freehire_compat.run(apply=True, drain_backlog=True, limit=1,
        db=db, client=client(monkeypatch), request_budget=RequestBudget(0))
    assert result["llm_requests"] == 0
    assert db.rpc_names == []
    assert row == before


def test_exhaustion_does_not_schedule_a_classifier_retry(monkeypatch):
    monkeypatch.setattr(llm_client.litellm, "completion", lambda **_: response('{"jobs":[]}'))
    sleeps = []
    outcome = freehire_compat.classify_batch(
        [{"job_id": "1"}], client=client(monkeypatch), max_requests=1,
        sleep_fn=sleeps.append)
    assert outcome.retries == 0
    assert sleeps == []


@pytest.mark.parametrize("cap", [1, 2])
@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_real_litellm_provider_http_attempts_obey_cap(monkeypatch, cap, provider):
    import httpx

    calls = []

    def send(self, request, **kwargs):
        calls.append(request)
        return httpx.Response(503, request=request, json={
            "error": {"code": 503, "message": "service unavailable", "status": "UNAVAILABLE"}})

    monkeypatch.setattr(httpx.Client, "send", send)
    real_client = client(monkeypatch)
    real_client.api_key = "offline-test"
    if provider == "gemini":
        real_client.model_chain = ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-flash-lite"]
    else:
        real_client.model = "openai/gpt-5-mini"
        real_client.model_chain = None
    outcome = freehire_compat.classify_batch(
        [{"job_id": "1"}], client=real_client, max_requests=cap,
        sleep_fn=lambda _: None)
    assert len(calls) == outcome.requests == cap
    assert all(request.method == "POST" for request in calls)
    assert outcome.failures == {}
