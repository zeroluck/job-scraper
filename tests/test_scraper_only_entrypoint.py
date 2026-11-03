"""Original scraper entrypoint, boundary doubles, no network or LLM calls."""
import json
import llm_client
import linkedin_discovery as discovery
import scraper
from test_lane_scraper_orchestration import configuration
from test_scraper_only_manual import PendingRead


def test_original_entrypoint_drains_300_of_927_without_llm(monkeypatch, tmp_path):
    task_limit, physical_limit = 300, 800
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID", "123")
    monkeypatch.setenv("LINKEDIN_DETAIL_ONLY_SEQUENCE", "456")
    monkeypatch.setattr(discovery.supabase_utils, "supabase", PendingRead(927))
    configured = configuration()
    configured = configured.model_copy(update={"settings": configured.settings.model_copy(update={
        "options": {**configured.settings.options, "max_detail_tasks_per_run": task_limit,
                    "max_detail_http_attempts_per_run": physical_limit}})})
    monkeypatch.setenv("LINKEDIN_DISCOVERY_MODE", "adaptive_queue")
    monkeypatch.delenv("SCRAPE_ARCHETYPE", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(scraper.config, "SCRAPING_SOURCES", ["linkedin"])
    monkeypatch.setenv("SCRAPE_CONFIG_SOURCE", "db")
    monkeypatch.setattr(scraper, "load_scrape_configuration", lambda **kw: configured)
    execution = scraper.build_search_executions(configured)[0]
    definition = discovery.scope_definition(execution, scraper.config.LINKEDIN_JOB_TYPE,
                                            scraper.config.LINKEDIN_F_WT)
    key = discovery.scope_key(definition)
    cycle = {"cycle_id": 123, "discovery_sequence": 456, "search_status": "sealed",
             "pinned_user_agent": "offline-agent", "scopes": [{
                 "scope_key": key, "scope_definition": definition,
                 "query_scope": json.dumps({"query_id": execution.query.query_id}),
                 "status": "complete", "next_page": 2}]}
    monkeypatch.setattr(discovery.supabase_utils, "get_resumable_linkedin_discovery_cycle",
                        lambda **_: cycle)
    def forbidden(*args, **kwargs):
        raise AssertionError("sealed detail runner must not search, publish, or call LLM")
    monkeypatch.setattr(discovery, "_request_page", forbidden)
    monkeypatch.setattr(llm_client.litellm, "completion", forbidden)
    monkeypatch.setattr(llm_client.LLMClient, "generate_content", forbidden)
    monkeypatch.setattr(discovery.supabase_utils, "seal_linkedin_discovery_cycle", forbidden)
    monkeypatch.setattr(discovery.supabase_utils, "record_scrape_success", forbidden)
    resolutions = []
    monkeypatch.setattr(discovery.supabase_utils, "resolve_eligible_failed_linkedin_discovery_cycles",
                        lambda cycle_id: resolutions.append(cycle_id))
    tasks = [{"id": i, "source_job_id": str(i), "lease_token": f"lease-{i}",
              "first_ingestion_run_id": "original-run", "search_card": {},
              "provenance": {"lane": "technology_delivery"}} for i in range(927)]
    claims, heartbeats, saves, gates = [], [], [], []
    def claim(worker_id, **kwargs):
        assert kwargs["limit"] == 1
        task = tasks.pop(0)
        claims.append((worker_id, task))
        return [task]
    monkeypatch.setattr(discovery.supabase_utils, "claim_linkedin_discovery_tasks", claim)
    monkeypatch.setattr(discovery.supabase_utils, "heartbeat_linkedin_discovery_task",
                        lambda *args: heartbeats.append(args))
    def detail(source_id, **kwargs):
        gate = kwargs["durable_gate"]
        assert isinstance(gate, discovery.DurableLinkedInRequestGate)
        gates.append(gate)
        assert kwargs["physical_limit"] == physical_limit
        assert kwargs["deadline"] > discovery.time.monotonic()
        assert kwargs["request_key"].endswith(f":lease-{source_id}:{source_id}")
        kwargs["physical_attempts"][0] += 1
        return {"job_id": source_id, "company": "Example", "job_title": "TPM"}, {"description": "Delivery"}
    monkeypatch.setattr(scraper, "_fetch_linkedin_job_details", detail)
    def apply(task, worker_id, job, **kwargs):
        assert job["scrape_run_id"] == "original-run"
        assert "technology_delivery" in kwargs["runtime_profiles"]
        saves.append((task["id"], worker_id, task["lease_token"]))
        return f"canonical-{task['id']}"
    monkeypatch.setattr(discovery.supabase_utils, "apply_linkedin_discovery_task_canonical", apply)
    assert scraper.main() == [f"canonical-{i}" for i in range(300)]
    assert len(tasks) == 627
    assert len(gates) == 300 and all(g is gates[0] for g in gates)
    assert heartbeats == saves == [(t["id"], w, t["lease_token"]) for w, t in claims]
    assert resolutions == [123]  # Existing guarded resolver retained, not publication.