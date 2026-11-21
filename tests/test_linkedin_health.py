from datetime import datetime, timedelta, timezone
from scripts.linkedin_health import assess, expected_dispatches


def test_requested_slots_preserve_wall_clock_across_dst():
    start=datetime(2026,10,31,4,tzinfo=timezone.utc)
    end=datetime(2026,11,2,5,tzinfo=timezone.utc)
    assert len(expected_dispatches(start,end))==28


def test_stale_publication_is_visible_with_empty_queue_and_green_runs():
    now=datetime(2026,11,21,20,tzinfo=timezone.utc)
    metrics,alerts=assess({"actionable_tasks":0,"leased_tasks":0,
        "covered_through_at":(now-timedelta(hours=2)).isoformat(),
        "publication":{"published_at":"2026-10-09T05:55:59Z","generation":71,"row_count":23745},
        "predecessor_ids":[50,51],"coverage_debt_count":65},[],now=now)
    assert metrics["publication_rows"]==23745
    assert metrics["expected_dispatches_7d"]==98
    assert any("publication_age" in a for a in alerts)
    assert any("scheduled_dispatches" in a for a in alerts)
    assert not any("covered_through_age" in a for a in alerts)
