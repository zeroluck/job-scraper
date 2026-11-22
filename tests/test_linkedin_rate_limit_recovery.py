"""Recoverable throttles stay inside the original grant/lease and physical caps."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

import linkedin_discovery as discovery
from linkedin_source_policy import ConsumedGrant, LinkedInRateLimited, LinkedInRequestDeadlineExceeded
import scraper


class Gate:
    def __init__(self):
        self.grants=[]
        self.finished=[]

    def acquire(self,kind,key,**kwargs):
        grant=ConsumedGrant(f"g{len(self.grants)}",datetime.now(timezone.utc)+timedelta(seconds=60*len(self.grants)))
        self.grants.append((kind,key,grant))
        return grant

    def finish(self,grant,response_class,status,**kwargs):
        self.finished.append((grant.grant_id,response_class,status))


def transport(monkeypatch,kind,statuses):
    calls=[]
    remaining=iter(statuses)
    html=(Path(__file__).parent/"fixtures/linkedin_job_detail_recruiter.html").read_bytes()
    def send(adapter,request,**kwargs):
        assert adapter.max_retries.total==0
        calls.append(request.url)
        response=requests.Response()
        response.status_code=next(remaining)
        response.url=request.url
        response.request=request
        response.headers["Content-Type"]="text/html"
        if response.status_code==429:
            response.headers["Retry-After"]="60"
        response._content=html if kind=="detail" else b"<!DOCTYPE html>\n\n<!---->  "
        return response
    monkeypatch.setattr(requests.adapters.HTTPAdapter,"send",send)
    return calls


def fetch(kind,gate,attempts,limit=10):
    if kind=="detail":
        return scraper._fetch_linkedin_job_details("4428124095",durable_gate=gate,user_agent="ua",
            request_key="task:7:00000000-0000-0000-0000-000000000007:4428124095",
            physical_attempts=attempts,physical_limit=limit)
    return discovery._request_page({"scope_key":"scope","source_window_earliest_at":"2026-11-20T00:00:00Z",
        "query":"TPM","location":"Canada","job_type":"F","work_types":"1,2,3"},1,
        user_agent="ua",gate=gate,parse_cards=lambda _:[],physical_attempts=attempts,physical_limit=limit)


@pytest.mark.parametrize("kind",["search","detail"])
def test_isolated_429_recovers_with_a_fresh_grant(monkeypatch,kind):
    calls=transport(monkeypatch,kind,[429,200])
    monkeypatch.setattr(scraper.time,"sleep",lambda _:pytest.fail("the shared gate owns the 429 cooldown"))
    gate=Gate();attempts=[0]
    assert fetch(kind,gate,attempts)
    assert len(calls)==len(gate.grants)==attempts[0]==2
    assert [r[2] for r in gate.finished]==[429,200]
    assert gate.grants[0][1].rsplit(":",1)[0]==gate.grants[1][1].rsplit(":",1)[0]


@pytest.mark.parametrize("kind",["search","detail"])
def test_sustained_429_remains_alertable_and_physically_bounded(monkeypatch,kind):
    monkeypatch.setattr(scraper.config,"MAX_RETRIES",2)
    calls=transport(monkeypatch,kind,[429,429,429])
    gate=Gate();attempts=[0]
    with pytest.raises((LinkedInRateLimited,discovery.DiscoveryRateLimited)):
        fetch(kind,gate,attempts)
    assert len(calls)==len(gate.grants)==attempts[0]==3


@pytest.mark.parametrize("kind",["search","detail"])
def test_rate_limit_retry_cannot_exceed_physical_invocation_budget(monkeypatch,kind):
    calls=transport(monkeypatch,kind,[429])
    gate=Gate();attempts=[0]
    with pytest.raises((LinkedInRateLimited,discovery.DiscoveryRateLimited)):
        fetch(kind,gate,attempts,limit=1)
    assert len(calls)==len(gate.grants)==attempts[0]==1


@pytest.mark.parametrize("kind",["search","detail"])
def test_unrecovered_429_is_not_disguised_as_pure_local_budget_exhaustion(monkeypatch,kind):
    calls=transport(monkeypatch,kind,[429])
    class LimitedGate(Gate):
        def acquire(self,*args,**kwargs):
            if self.grants:
                raise LinkedInRequestDeadlineExceeded("cooldown cannot fit")
            return super().acquire(*args,**kwargs)
    gate=LimitedGate();attempts=[0]
    with pytest.raises((LinkedInRateLimited,discovery.DiscoveryRateLimited)):
        fetch(kind,gate,attempts)
    assert len(calls)==len(gate.grants)==attempts[0]==1


def test_a_prior_429_does_not_count_as_a_404_confirmation(monkeypatch):
    calls=transport(monkeypatch,"detail",[429,404,404])
    monkeypatch.setattr(scraper.time,"sleep",lambda _:None)
    gate=Gate();attempts=[0]
    result=fetch("detail",gate,attempts)
    assert result.confirmed_terminal_unavailable
    assert [r[1:] for r in gate.finished]==[("http_error",429),("not_found_unconfirmed",404),("terminal_unavailable",404)]
    assert len(calls)==attempts[0]==3
