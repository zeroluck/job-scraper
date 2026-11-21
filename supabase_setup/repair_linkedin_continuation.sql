-- Authoritative copy; mirror into the companion web migration chain.
-- Preserve execution timestamps and derive continuation from exact page proof.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

CREATE OR REPLACE FUNCTION public.prepare_linkedin_discovery_scope_state(
    p_scope_keys text[], p_recovery_floor timestamptz
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    scope_key_value text;
    states jsonb;
    debt_rows jsonb;
BEGIN
    IF p_scope_keys IS NULL OR array_length(p_scope_keys, 1) IS NULL OR p_recovery_floor IS NULL THEN
        RAISE EXCEPTION 'scope keys and recovery floor are required' USING ERRCODE = '22023';
    END IF;
    FOREACH scope_key_value IN ARRAY p_scope_keys LOOP
        PERFORM public.expire_linkedin_coverage_debt(scope_key_value, p_recovery_floor);
    END LOOP;
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'scope_key', state.scope_key,
        'last_operational_success_at', state.last_operational_success_at,
        'last_covered_through_at', proof.covered_through,
        'last_operational_discovery_sequence', state.last_operational_discovery_sequence,
        'recommended_pages', state.recommended_pages,
        'coverage_debt', state.coverage_debt,
        'last_deep_sweep_at', state.last_deep_sweep_at
    ) ORDER BY state.scope_key), '[]'::jsonb) INTO states
    FROM public.linkedin_scope_coverage_state state
    LEFT JOIN LATERAL (
        SELECT LEAST(scope.source_window_latest_at, page.latest) AS covered_through
        FROM public.linkedin_discovery_cycles cycle
        JOIN public.linkedin_discovery_cycle_scopes scope ON scope.discovery_cycle_id = cycle.id
        JOIN public.ingestion_runs run ON run.id = scope.ingestion_run_id
        CROSS JOIN LATERAL (
            SELECT count(*) AS pages, min(p.page_number) AS first_page,
                   max(p.page_number) AS last_page,
                   max(p.source_window_earliest_at) AS earliest,
                   min(p.source_window_latest_at) AS latest,
                   (array_agg(p.result ORDER BY p.page_number DESC))[1] AS last_result
            FROM public.linkedin_ingestion_pages p WHERE p.ingestion_run_id = scope.ingestion_run_id
        ) page
        WHERE cycle.discovery_sequence = state.last_operational_discovery_sequence
          AND scope.scope_key = state.scope_key AND cycle.search_status = 'sealed'
          AND scope.status = 'complete' AND run.status = 'complete'
          AND run.coverage_status = 'exhausted'
          AND page.first_page = 1 AND page.pages = page.last_page
          AND page.last_result = 'no_results'
          AND page.earliest <= scope.source_window_earliest_at
          AND page.latest >= scope.source_window_latest_at
    ) proof ON true
    WHERE state.scope_key = ANY(p_scope_keys);
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'scope_key', selected.scope_key,
        'source_window_earliest_at', selected.source_window_earliest_at,
        'source_window_latest_at', selected.source_window_latest_at,
        'created_at', selected.created_at
    ) ORDER BY selected.scope_key), '[]'::jsonb) INTO debt_rows
    FROM (
        SELECT DISTINCT ON (debt.scope_key) debt.scope_key, debt.source_window_earliest_at,
               debt.source_window_latest_at, debt.created_at
        FROM public.linkedin_coverage_debt debt
        WHERE debt.scope_key = ANY(p_scope_keys) AND debt.status = 'pending'
        ORDER BY debt.scope_key, debt.source_window_earliest_at, debt.id
    ) selected;
    RETURN jsonb_build_object('states', states, 'debt', debt_rows);
END;
$$;

-- One predicate for the manual preflight and its execution guard. The selector
-- intentionally also retains future retries and leases until they settle.
CREATE OR REPLACE FUNCTION public.linkedin_actionable_task_count()
RETURNS bigint LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $$
    SELECT count(*) FROM public.linkedin_discovery_tasks
    WHERE status IN ('pending', 'failed_retryable') AND attempt_count < max_attempts
      AND available_at <= statement_timestamp();
$$;
REVOKE ALL ON FUNCTION public.linkedin_actionable_task_count() FROM PUBLIC;

-- Native functions have separate least-privilege owners. Hosted installations
-- retain their existing owners. Do not replace either authorization model.
DO $$
DECLARE
    owner_name text;
    table_name text;
BEGIN
    SELECT pg_get_userbyid(proowner) INTO owner_name FROM pg_proc
    WHERE oid = 'public.prepare_linkedin_discovery_scope_state(text[],timestamptz)'::regprocedure;
    IF owner_name LIKE 'jobs_o_%' THEN
        FOREACH table_name IN ARRAY ARRAY['linkedin_discovery_cycles', 'linkedin_discovery_cycle_scopes',
                                         'linkedin_ingestion_pages', 'ingestion_runs'] LOOP
            EXECUTE format('GRANT SELECT ON public.%I TO %I', table_name, owner_name);
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                           AND tablename = table_name AND policyname = 'continuation_proof_select') THEN
                EXECUTE format('CREATE POLICY continuation_proof_select ON public.%I FOR SELECT TO %I USING (true)', table_name, owner_name);
            END IF;
        END LOOP;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'job_runner') THEN
        GRANT EXECUTE ON FUNCTION public.linkedin_actionable_task_count() TO job_runner;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT EXECUTE ON FUNCTION public.linkedin_actionable_task_count() TO service_role;
    END IF;
END;
$$;
COMMIT;
