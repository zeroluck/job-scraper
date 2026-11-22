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


def test_job_queue_wait_is_not_hidden_by_equal_run_start_metadata():
    now=datetime(2026,11,21,20,tzinfo=timezone.utc)
    created=now-timedelta(hours=1)
    metrics,_=assess({},[{"event":"schedule","createdAt":created.isoformat(),
        "startedAt":created.isoformat(),"scrapeStartedAt":(created+timedelta(minutes=17)).isoformat()}],now=now)
    assert metrics["max_run_start_delay_seconds"]==0
    assert metrics["max_scrape_job_start_delay_seconds"]==1020
    assert metrics["scrape_job_start_observations"]==1


def test_rate_limited_checkpoint_still_emits_an_actionable_cooldown_alert():
    now=datetime(2026,11,22,22,tzinfo=timezone.utc)
    metrics,alerts=assess({"actionable_tasks":668,"source_policy":{
        "cooldown_until":(now+timedelta(seconds=120)).isoformat(),"circuit_state":"closed"}},[],now=now)
    assert metrics["source_cooldown_remaining_seconds"]==120
    assert any("shared cooldown active" in alert for alert in alerts)
