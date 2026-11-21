"""Read-only freshness/dispatch measurements; no finalizer or worker calls."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def expected_dispatches(start, end):
    zone = ZoneInfo("America/New_York")
    day = start.astimezone(zone).date()
    final_day = end.astimezone(zone).date()
    slots = []
    while day <= final_day:
        for hour in [0, *range(9, 22)]:
            slot = datetime(day.year, day.month, day.day, hour, 23, tzinfo=zone)
            if start <= slot <= end:
                slots.append(slot.astimezone(timezone.utc))
        day += timedelta(days=1)
    return slots


def assess(diagnostic, runs, *, now):
    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    def age(value):
        timestamp=parse(value)
        return max(0, (now-timestamp).total_seconds()) if timestamp else None
    start=now-timedelta(days=7)
    scheduled=[r for r in runs if r["event"]=="schedule" and start <= parse(r["createdAt"]) <= now]
    nominal=len(expected_dispatches(start,now))
    publication=diagnostic.get("publication") or {}
    classification=diagnostic.get("classification") or {}
    metrics={
        "expected_dispatches_7d":nominal,"actual_scheduled_dispatches_7d":len(scheduled),
        "dispatch_ratio_7d":len(scheduled)/nominal if nominal else None,
        "max_run_start_delay_seconds":max((max(0,(parse(r["startedAt"])-parse(r["createdAt"])).total_seconds()) for r in scheduled if r.get("startedAt")),default=None),
        "max_scrape_job_start_delay_seconds":max((max(0,(parse(r["scrapeStartedAt"])-parse(r["createdAt"])).total_seconds()) for r in scheduled if r.get("scrapeStartedAt")),default=None),
        "scrape_job_start_observations":sum(bool(r.get("scrapeStartedAt")) for r in scheduled),
        "covered_through_age_seconds":age(diagnostic.get("covered_through_at")),
        "last_source_request_age_seconds":age(diagnostic.get("last_request_at")),
        "classification_pending_age_seconds":age(classification.get("oldest_pending_at")),
        "classification_claim_age_seconds":age(classification.get("oldest_claim_at")),
        "publication_age_seconds":age(publication.get("published_at")),
        "actionable_tasks":diagnostic.get("actionable_tasks"),"leased_tasks":diagnostic.get("leased_tasks"),
        "publication_generation":publication.get("generation"),"publication_rows":publication.get("row_count"),
        "predecessor_ids":diagnostic.get("predecessor_ids"),"coverage_debt_count":diagnostic.get("coverage_debt_count"),
        "source_policy":diagnostic.get("source_policy"),
        "dispatch_interpretation":"Requested versus recorded events; does not establish why events were omitted. Scrape job start minus run creation measures observed dispatch/concurrency/runner wait together; run-start metadata alone does not measure that wait."
    }
    metrics["classification_age_basis"]="Pending age is canonical first_seen_at, not time entering pending status; pending_since is not persisted. Claim age uses the actual claim timestamp."
    alerts=[]
    for key,limit in (("covered_through_age_seconds",36*3600),("classification_pending_age_seconds",24*3600),
                      ("classification_claim_age_seconds",30*60),("publication_age_seconds",24*3600)):
        if metrics[key] is not None and metrics[key]>limit:
            alerts.append(f"{key}={round(metrics[key])} exceeds {limit}")
    if nominal and len(scheduled)<nominal*.8:
        alerts.append(f"scheduled_dispatches_7d={len(scheduled)}/{nominal}; investigate dispatch/start gaps")
    if metrics["max_scrape_job_start_delay_seconds"] is not None and metrics["max_scrape_job_start_delay_seconds"]>3600:
        alerts.append("scrape job start delayed more than 3600 seconds; inspect workflow concurrency and runner queue")
    policy=diagnostic.get("source_policy") or {}
    if policy.get("circuit_state")=="open":
        alerts.append("LinkedIn challenge circuit open; investigate retained denial evidence")
    return metrics,alerts


def main():
    import config
    from data_client import create_data_client
    db=create_data_client(config)
    diagnostic=db.rpc("linkedin_publication_diagnostics",{"p_cycle_id":None}).execute().data
    repo=os.getenv("GITHUB_REPOSITORY","zeroluck/job-scraper")
    runs=json.loads(subprocess.check_output(["gh","run","list","--repo",repo,
        "--workflow","scrape_jobs.yml","--limit","1000","--json","databaseId,event,createdAt,startedAt,status,conclusion,headSha"],text=True))
    now=datetime.now(timezone.utc)
    for run in runs:
        if run["event"]!="schedule" or datetime.fromisoformat(run["createdAt"].replace("Z","+00:00"))<now-timedelta(days=7):
            continue
        jobs=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/actions/runs/{run['databaseId']}/jobs"],text=True))["jobs"]
        scrape=next((job for job in jobs if job["name"]=="scrape"),None)
        if scrape and scrape.get("started_at") and not scrape["started_at"].startswith("0001-"):
            run["scrapeStartedAt"]=scrape["started_at"]
    metrics,alerts=assess(diagnostic,runs,now=now)
    print(json.dumps({"metrics":metrics,"alerts":alerts},indent=2))
    for alert in alerts:
        print("::warning::"+alert)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as output:
            output.write("## LinkedIn health (read-only)\n```json\n"+json.dumps({"metrics":metrics,"alerts":alerts},indent=2)+"\n```\n")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a") as output:
            output.write("alerts="+"; ".join(alerts)+"\n")


if __name__=="__main__":
    main()
