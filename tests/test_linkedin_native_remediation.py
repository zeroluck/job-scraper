"""Opt-in isolated PG17 qualification using a freshly captured native schema.

Set LINKEDIN_NATIVE_SCHEMA and LINKEDIN_NATIVE_CATALOG to read-only captures.
No database credentials, production rows, or source network access are used.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ["reconcile_linkedin_actionable_selector.sql", "repair_linkedin_continuation.sql", "repair_linkedin_retry_accounting.sql", "linkedin_durable_throttling.sql", "linkedin_publication_diagnostics.sql"]


def test_authoritative_sql_matches_required_web_history_mirror():
    import difflib
    mirror=ROOT.parent/"job-scraper-web/supabase/migrations/20261121195836_linkedin_ingestion_remediation.sql"
    if not mirror.exists():
        pytest.skip("companion checkout absent")
    expected="\n".join((ROOT/"supabase_setup"/name).read_text() for name in MIGRATIONS)
    actual="\n".join(mirror.read_text().splitlines()[3:])+"\n"
    assert actual==expected, "".join(difflib.unified_diff(expected.splitlines(True),actual.splitlines(True)))


@pytest.fixture(scope="module")
def native():
    schema = os.getenv("LINKEDIN_NATIVE_SCHEMA")
    catalog = os.getenv("LINKEDIN_NATIVE_CATALOG")
    if not schema or not catalog:
        pytest.skip("fresh native schema/catalog capture not supplied")
    name = "linkedin-remediation-test-" + uuid.uuid4().hex[:10]
    def sql(text, *, role=None, check=True):
        if role:
            text = f"SET ROLE {role};\n" + text
        result = subprocess.run(["docker", "exec", "-i", name, "psql", "-XqAt", "-h", "127.0.0.1", "-U", "postgres",
                                 "-v", "ON_ERROR_STOP=1"], input=text, text=True, capture_output=True)
        if check:
            assert result.returncode == 0, result.stderr
        return result
    subprocess.run(["docker", "run", "-d", "--name", name, "--network", "none",
                    "--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                    "postgres:17.11"], check=True, capture_output=True)
    try:
        for _ in range(200):
            if sql("SELECT 1", check=False).returncode == 0:
                break
            time.sleep(.1)
        else:
            pytest.fail("isolated PostgreSQL did not start")
        for role in json.loads(Path(catalog).read_text())["roles"]:
            if role["rolname"] == "postgres" or role["rolname"].startswith("pg_"):
                continue
            assert not role["rolsuper"] and not role["rolbypassrls"], role["rolname"]
            sql('CREATE ROLE "' + role["rolname"].replace('"', '""') + '" NOLOGIN;')
        sql(Path(schema).read_text())
        for _ in range(2):
            for migration in MIGRATIONS:
                sql((ROOT / "supabase_setup" / migration).read_text())
        sql("""
INSERT INTO public.linkedin_source_request_policy(source,minimum_interval_ms) VALUES ('linkedin',2500);
INSERT INTO public.linkedin_discovery_cycles(id,execution_id,discovery_sequence,config_content_hash,required_scope_count,pinned_user_agent)
OVERRIDING SYSTEM VALUE VALUES(1,'00000000-0000-0000-0000-000000000001',1,repeat('0',64),1,'fixture');
INSERT INTO public.ingestion_runs(id,provider,discovery_cycle_id,status,coverage_status)
VALUES ('00000000-0000-0000-0000-000000000001','linkedin',1,'complete','exhausted');
INSERT INTO public.linkedin_scope_coverage_state(scope_key,scope_definition_hash,scope_definition,config_content_hash,archetype,query_id,geography_id)
VALUES ('scope-a',repeat('0',64),'{}',repeat('0',64),'fixture','fixture','fixture');
INSERT INTO public.linkedin_discovery_cycle_scopes(discovery_cycle_id,scope_key,ingestion_run_id,query_scope,request_anchor_at,source_window_earliest_at,source_window_latest_at,minimum_pages,target_pages,status,enqueue_committed_at)
VALUES (1,'scope-a','00000000-0000-0000-0000-000000000001','{}','2026-11-20T00:00Z','2026-11-19T00:00Z','2026-11-20T00:00Z',1,1,'complete',now());
INSERT INTO public.linkedin_ingestion_pages(ingestion_run_id,page_number,page_start,requested_at,source_window_earliest_at,source_window_latest_at,element_count,card_count,result,request_attempts,elapsed_ms,classifier_version,response_fingerprint,membership_fingerprint)
VALUES ('00000000-0000-0000-0000-000000000001',1,0,'2026-11-20T00:00Z','2026-11-19T00:00Z','2026-11-20T00:00Z',0,0,'no_results',1,1,'fixture',repeat('0',64),repeat('0',64));
""")
        yield sql
    finally:
        subprocess.run(["docker", "rm", "-fv", name], check=True, capture_output=True)


def test_real_runner_seal_and_page_frontier(native):
    sealed=json.loads(native("SELECT public.seal_linkedin_discovery_cycle(1,false)", role="job_runner").stdout)
    assert sealed["cycle_id"] == 1
    result=json.loads(native("SELECT public.prepare_linkedin_discovery_scope_state(ARRAY['scope-a'],'2026-11-01')", role="job_runner").stdout)
    state=result["states"][0]
    assert state["last_covered_through_at"] == "2026-11-20T00:00:00+00:00"
    assert state["last_operational_success_at"] != state["last_covered_through_at"]
    native("UPDATE public.linkedin_ingestion_pages SET page_number=2")
    result=json.loads(native("SELECT public.prepare_linkedin_discovery_scope_state(ARRAY['scope-a'],'2026-11-01')", role="job_runner").stdout)
    assert result["states"][0]["last_covered_through_at"] is None
    native("UPDATE public.linkedin_ingestion_pages SET page_number=1")


def test_claim_local_deferral_then_retry_only_source_attempt(native):
    native("""INSERT INTO public.linkedin_discovery_tasks(source_job_id,requirement_key,first_ingestion_run_id,first_query_scope,first_observed_at,latest_observed_at,search_card)
VALUES ('fixture','first','00000000-0000-0000-0000-000000000001','{}',now(),now(),'{}');""")
    task=json.loads(native("SELECT row_to_json(t) FROM public.claim_linkedin_discovery_tasks('worker',1,'oldest') t", role="job_runner").stdout)
    assert task["attempt_count"] == 0
    native(f"SELECT public.transition_linkedin_discovery_task({task['id']},'worker','{task['lease_token']}','failed_retryable',NULL,'local_budget_deferred')",role="job_runner")
    native("UPDATE public.linkedin_discovery_tasks SET available_at=now()")
    assert native("SELECT public.linkedin_actionable_task_count()",role="job_runner").stdout.strip()=="1"
    task=json.loads(native("SELECT row_to_json(t) FROM public.claim_linkedin_discovery_tasks('worker',1,'oldest') t",role="job_runner").stdout)
    prefix=f"task:{task['id']}:{task['lease_token']}:fixture"
    for attempt in range(2):
        native("UPDATE public.linkedin_source_request_policy SET next_allowed_at=now(),cooldown_until=now()")
        grant=json.loads(native(f"SELECT public.acquire_linkedin_request_grant('adaptive-detail','detail','{prefix}:{attempt}')",role="job_runner").stdout)
        assert grant["consumed"] is True
        assert native("SELECT attempt_count FROM public.linkedin_discovery_tasks",role="job_runner").stdout.strip()=="1"
        assert native(f"SELECT public.finish_linkedin_request_grant('{grant['grant_id']}','adaptive-detail','http_error',503)",role="job_runner").stdout.strip()=="t"
    native("UPDATE public.linkedin_discovery_tasks SET lease_expires_at=now()-interval '1 second'")
    denied=native(f"SELECT public.acquire_linkedin_request_grant('adaptive-detail','detail','{prefix}:2')",role="job_runner",check=False)
    # Spacing can defer the invalid lease before lease validation; once ready it must reject.
    native("UPDATE public.linkedin_source_request_policy SET next_allowed_at=now()")
    denied=native(f"SELECT public.acquire_linkedin_request_grant('adaptive-detail','detail','{prefix}:2')",role="job_runner",check=False)
    assert denied.returncode and 'active task lease' in denied.stderr


def test_shared_cooldown_survives_new_connections_and_all_producers(native):
    native("UPDATE public.linkedin_source_request_policy SET next_allowed_at=now(),cooldown_until=now()")
    grant=json.loads(native("SELECT public.acquire_linkedin_request_grant('producer-a','search','fixture')",role="job_runner").stdout)
    assert native(f"SELECT public.finish_linkedin_request_feedback('{grant['grant_id']}','producer-a','http_error',429,180,'{{\"retry-after\":\"180\"}}','{{\"run_id\":\"fixture\"}}')",role="job_runner").stdout.strip()=="t"
    for producer in ("adaptive-discovery","backfill","job-manager"):
        result=json.loads(native(f"SELECT public.acquire_linkedin_request_grant('{producer}','search','restart')",role="job_runner").stdout)
        assert result["outcome"]=="wait" and result["wait_ms"]>0
    policy=json.loads(native("SELECT row_to_json(p) FROM public.linkedin_source_request_policy p").stdout)
    assert policy["effective_interval_ms"]==10000 and policy["consecutive_429"]==1
    # Duplicate completion must not apply feedback twice.
    assert native(f"SELECT public.finish_linkedin_request_grant('{grant['grant_id']}','producer-a','http_error',429)",role="job_runner").stdout.strip()=="f"
    native("UPDATE public.linkedin_source_request_policy SET cooldown_until=now(),next_allowed_at=now()")
    grant=json.loads(native("SELECT public.acquire_linkedin_request_grant('producer-b','search','fixture')",role="job_runner").stdout)
    native(f"SELECT public.open_linkedin_source_circuit('{grant['grant_id']}','producer-b','real challenge',999)",role="job_runner")
    assert json.loads(native("SELECT public.acquire_linkedin_request_grant('producer-c','search','fixture')",role="job_runner").stdout)["outcome"]=="circuit_open"


def test_anonymous_roles_cannot_use_mutating_rpcs(native):
    for role in ("anon","authenticated"):
        for call in ("public.linkedin_actionable_task_count()", "public.finish_linkedin_request_feedback(NULL,'x','x',429,NULL,'{}','{}')"):
            result=native("SELECT "+call,role=role,check=False)
            assert result.returncode and "permission denied" in result.stderr


def test_diagnostic_runs_as_real_runner_without_finalizing(native):
    result=json.loads(native("SELECT public.linkedin_publication_diagnostics(1)",role="job_runner").stdout)
    assert result["requested_cycle_id"]==1
    assert result["predecessor_ids"]==[]
    assert result["requirement_count"]==0
    assert result["publication"] is None
