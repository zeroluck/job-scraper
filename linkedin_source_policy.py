from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import supabase_utils


class LinkedInCircuitOpen(RuntimeError):
    pass


class LinkedInGrantRejected(RuntimeError):
    pass


class LinkedInRequestDeadlineExceeded(TimeoutError):
    pass


def linkedin_challenge_evidence(response: Any) -> str | None:
    status_code = getattr(response, "status_code", None)
    if status_code in (403, 999):
        return f"http_status={status_code}"

    url = str(getattr(response, "url", "") or "")
    path = urlparse(url).path.lower()
    if "/checkpoint/" in path:
        return "final_url_checkpoint"
    if "/challenge/" in path:
        return "final_url_challenge"

    headers = getattr(response, "headers", {}) or {}
    if str(headers.get("cf-mitigated", "")).lower() == "challenge":
        return "cf_mitigated_challenge"

    text = getattr(response, "text", "") or ""
    if not text:
        return None
    soup = BeautifulSoup(text[:8_192], "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if title in {
        "security verification",
        "security verification | linkedin",
        "security verification - linkedin",
    }:
        return f"challenge_title={title!r}"
    if soup.find(id="challenge-page"):
        return "challenge_page_element"
    if soup.find("form", action=lambda value: value and (
        "/checkpoint/" in value.lower() or "/challenge/" in value.lower()
    )) is not None:
        return "challenge_form_action"
    return None


def is_linkedin_challenge(response: Any) -> bool:
    return linkedin_challenge_evidence(response) is not None


@dataclass(frozen=True)
class ConsumedGrant:
    grant_id: str
    started_at: datetime


class DurableLinkedInRequestGate:
    def __init__(self, producer: str, *, db: Any = None) -> None:
        self.producer = producer
        self.db = db

    def acquire(
        self,
        request_kind: str,
        request_key: str,
        *,
        deadline: float | None = None,
    ) -> ConsumedGrant:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise LinkedInRequestDeadlineExceeded(
                    "LinkedIn request deadline elapsed before grant acquisition"
                )
            grant = supabase_utils.acquire_linkedin_request_grant(
                self.producer,
                request_kind,
                request_key,
                db=self.db,
            )
            outcome = grant.get("outcome")
            if outcome == "circuit_open":
                raise LinkedInCircuitOpen(str(grant.get("reason") or "LinkedIn circuit is open"))
            if outcome == "wait":
                wait_ms = grant.get("wait_ms")
                if not isinstance(wait_ms, int) or wait_ms < 0:
                    raise LinkedInGrantRejected("request grant returned an invalid wait")
                wait_seconds = min(wait_ms / 1000, 60)
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or wait_seconds >= remaining:
                        raise LinkedInRequestDeadlineExceeded(
                            "LinkedIn request deadline elapsed while waiting for a grant"
                        )
                time.sleep(wait_seconds)
                continue
            if outcome != "grant" or not grant.get("grant_id"):
                raise LinkedInGrantRejected("request grant was rejected")
            if grant.get("consumed") is True:
                started_at = grant.get("started_at")
                if not isinstance(started_at, str):
                    raise LinkedInGrantRejected("consumed grant omitted started_at")
                return ConsumedGrant(
                    grant_id=str(grant["grant_id"]),
                    started_at=datetime.fromisoformat(
                        started_at.replace("Z", "+00:00")
                    ),
                )
            consumed = supabase_utils.consume_linkedin_request_grant(
                str(grant["grant_id"]), self.producer, db=self.db
            )
            if not consumed.get("consumed"):
                if consumed.get("reason") == "circuit_open":
                    raise LinkedInCircuitOpen("LinkedIn circuit opened before request start")
                continue
            started_at = consumed.get("started_at")
            if not isinstance(started_at, str):
                raise LinkedInGrantRejected("consumed grant omitted started_at")
            return ConsumedGrant(
                grant_id=str(grant["grant_id"]),
                started_at=datetime.fromisoformat(started_at.replace("Z", "+00:00")),
            )

    def finish(self, grant: ConsumedGrant, response_class: str, http_status: int | None) -> None:
        finished = supabase_utils.finish_linkedin_request_grant(
            grant.grant_id,
            self.producer,
            response_class,
            http_status,
            db=self.db,
        )
        if not finished:
            raise LinkedInGrantRejected("request grant was invalidated before completion")

    def open_circuit(
        self,
        grant: ConsumedGrant,
        reason: str,
        http_status: int | None,
    ) -> None:
        opened = supabase_utils.open_linkedin_source_circuit(
            grant.grant_id,
            self.producer,
            reason,
            http_status,
            db=self.db,
        )
        if not opened:
            raise LinkedInGrantRejected("request grant was invalidated before circuit open")
