import pytest

import linkedin_source_policy


def test_gate_waits_then_consumes_exact_grant(monkeypatch):
    grants = iter([
        {"outcome": "wait", "wait_ms": 250},
        {"outcome": "grant", "grant_id": "grant-1"},
    ])
    sleeps = []
    monkeypatch.setattr(
        linkedin_source_policy.supabase_utils,
        "acquire_linkedin_request_grant",
        lambda *_args, **_kwargs: next(grants),
    )
    monkeypatch.setattr(
        linkedin_source_policy.supabase_utils,
        "consume_linkedin_request_grant",
        lambda *_args, **_kwargs: {
            "consumed": True,
            "started_at": "2026-09-04T12:00:00Z",
        },
    )
    monkeypatch.setattr(linkedin_source_policy.time, "sleep", sleeps.append)

    grant = linkedin_source_policy.DurableLinkedInRequestGate("test").acquire(
        "detail", "source-1"
    )

    assert grant.grant_id == "grant-1"
    assert sleeps == [0.25]


def test_gate_propagates_open_circuit(monkeypatch):
    monkeypatch.setattr(
        linkedin_source_policy.supabase_utils,
        "acquire_linkedin_request_grant",
        lambda *_args, **_kwargs: {"outcome": "circuit_open", "reason": "challenge"},
    )

    with pytest.raises(linkedin_source_policy.LinkedInCircuitOpen, match="challenge"):
        linkedin_source_policy.DurableLinkedInRequestGate("test").acquire(
            "search", "scope-1"
        )


def test_gate_rejects_invalidated_finish(monkeypatch):
    monkeypatch.setattr(
        linkedin_source_policy.supabase_utils,
        "finish_linkedin_request_feedback",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(
        linkedin_source_policy.LinkedInGrantRejected, match="invalidated"
    ):
        linkedin_source_policy.DurableLinkedInRequestGate("test").finish(
            linkedin_source_policy.ConsumedGrant(
                "grant-1",
                linkedin_source_policy.datetime.fromisoformat(
                    "2026-09-04T12:00:00+00:00"
                ),
            ),
            "complete",
            200,
        )


def test_gate_does_not_sleep_past_request_deadline(monkeypatch):
    monkeypatch.setattr(
        linkedin_source_policy.supabase_utils,
        "acquire_linkedin_request_grant",
        lambda *_args, **_kwargs: {"outcome": "wait", "wait_ms": 1000},
    )
    monkeypatch.setattr(linkedin_source_policy.time, "monotonic", lambda: 10.0)

    with pytest.raises(linkedin_source_policy.LinkedInRequestDeadlineExceeded):
        linkedin_source_policy.DurableLinkedInRequestGate("test").acquire(
            "search", "scope-1", deadline=10.5
        )


def test_feedback_retains_retry_after_but_never_cookie_headers(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(linkedin_source_policy.supabase_utils,"finish_linkedin_request_feedback",
        lambda *args,**kwargs: calls.append((args,kwargs)) or True)
    gate=linkedin_source_policy.DurableLinkedInRequestGate("test")
    grant=linkedin_source_policy.ConsumedGrant("g",linkedin_source_policy.datetime.now())
    gate.finish(grant,"http_error",429,response=SimpleNamespace(headers={"Retry-After":"180","Set-Cookie":"private","Authorization":"private"}))
    assert calls[0][1]["retry_after_seconds"]==180
    assert calls[0][1]["response_headers"]=={"retry-after":"180"}


@pytest.mark.parametrize("kind",["search","detail"])
def test_redirect_cannot_multiply_physical_requests_under_one_grant(monkeypatch,kind):
    from datetime import datetime,timezone
    import requests
    import linkedin_discovery
    import scraper
    sends=[]
    class Gate:
        def acquire(self,*args,**kwargs):
            return linkedin_source_policy.ConsumedGrant("grant",datetime.now(timezone.utc))
        def finish(self,*args,**kwargs):
            pass
    def send(adapter,request,**kwargs):
        sends.append(request.url)
        assert adapter.max_retries.total==0
        response=requests.Response()
        response.status_code=302
        response.headers["Location"]="https://www.linkedin.com/checkpoint/challenge"
        response.url=request.url
        response.request=request
        response._content=b""
        return response
    monkeypatch.setattr(requests.adapters.HTTPAdapter,"send",send)
    attempts=[0]
    with pytest.raises((linkedin_discovery.DiscoveryError,scraper.LinkedInRequestFailed)):
        if kind=="search":
            linkedin_discovery._request_page({"scope_key":"scope","query":"TPM","location":"Canada",
                "job_type":"F","work_types":"1,2,3","source_window_earliest_at":"2026-11-20T00:00:00Z"},1,
                user_agent="ua",gate=Gate(),parse_cards=lambda _:[],physical_attempts=attempts,physical_limit=10)
        else:
            scraper._fetch_linkedin_job_details("fixture",durable_gate=Gate(),physical_attempts=attempts,physical_limit=10)
    assert len(sends)==attempts[0]==1


@pytest.mark.parametrize("kind",["search","detail"])
def test_grant_wait_reserves_request_time_without_a_physical_attempt(monkeypatch,kind):
    import linkedin_discovery
    import scraper
    attempts=[0]
    class Gate:
        def acquire(self,*args,**kwargs):
            assert kwargs["deadline"]==1000-scraper.config.REQUEST_TIMEOUT
            raise linkedin_source_policy.LinkedInRequestDeadlineExceeded("no full request fits")
    monkeypatch.setattr(scraper.requests,"get",lambda *args,**kwargs:pytest.fail("local deferral must not send"))
    with pytest.raises((linkedin_source_policy.LinkedInRequestDeadlineExceeded,linkedin_discovery.DiscoveryBudgetDeferred)):
        if kind=="search":
            linkedin_discovery._request_page({"scope_key":"s","source_window_earliest_at":"2026-11-20T00:00:00Z"},1,
                user_agent="ua",gate=Gate(),parse_cards=lambda _:[],physical_attempts=attempts,physical_limit=10,deadline=1000)
        else:
            scraper._fetch_linkedin_job_details("s",durable_gate=Gate(),physical_attempts=attempts,physical_limit=10,deadline=1000)
    assert attempts==[0]
