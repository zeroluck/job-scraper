-- Authoritative copy; mirror into the companion web migration chain.
-- Read-only visibility; does not finalize, accept, or resolve anything.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
CREATE OR REPLACE FUNCTION public.linkedin_publication_diagnostics(p_cycle_id bigint)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
WITH selected AS (
    SELECT id,discovery_sequence,search_status,search_completed_at
    FROM public.linkedin_discovery_cycles
    WHERE p_cycle_id IS NULL OR id=p_cycle_id ORDER BY discovery_sequence DESC LIMIT 1
), predecessors AS (
    SELECT c.id FROM public.linkedin_discovery_cycles c,selected
    WHERE c.discovery_sequence <= selected.discovery_sequence AND c.search_status <> 'sealed'
      AND NOT EXISTS (
        SELECT 1 FROM public.linkedin_discovery_cycle_resolutions r
        JOIN public.linkedin_discovery_cycles recovery ON recovery.id=r.resolving_discovery_cycle_id
        WHERE r.failed_discovery_cycle_id=c.id AND recovery.search_status='sealed'
          AND recovery.discovery_sequence <= selected.discovery_sequence
      )
), debt AS (
    SELECT d.id,d.status FROM public.linkedin_coverage_debt d
    JOIN public.linkedin_discovery_cycles c ON c.id=d.origin_discovery_cycle_id,selected
    WHERE c.discovery_sequence <= selected.discovery_sequence AND d.status IN ('pending','expired_unresolved')
), blockers AS (
    SELECT r.discovery_cycle_id,r.ingestion_run_id,r.provider,r.source_job_id,r.task_kind,r.requirement_key,
           t.id AS task_id,t.status,t.attempt_count,t.max_attempts,t.last_error_code,t.latest_observed_at
    FROM public.linkedin_discovery_requirements r
    JOIN public.linkedin_discovery_cycles c ON c.id=r.discovery_cycle_id
    JOIN public.linkedin_discovery_tasks t ON t.id=r.task_id
    LEFT JOIN public.listing_states s ON s.provider=t.provider AND s.source_job_id=t.source_job_id
    LEFT JOIN public.linkedin_discovery_requirement_acceptances a
      ON (a.discovery_cycle_id,a.ingestion_run_id,a.provider,a.source_job_id,a.task_kind,a.requirement_key)
       = (r.discovery_cycle_id,r.ingestion_run_id,r.provider,r.source_job_id,r.task_kind,r.requirement_key),selected
    WHERE c.discovery_sequence <= selected.discovery_sequence AND r.required AND a.discovery_cycle_id IS NULL
      AND (t.status='terminal_unavailable' OR (t.status='complete' AND t.canonical_job_id IS NOT NULL
           AND s.canonical_job_id=t.canonical_job_id)) IS NOT TRUE
)
SELECT jsonb_build_object(
    'requested_cycle_id',(SELECT id FROM selected),
    'discovery_sequence',(SELECT discovery_sequence FROM selected),
    'search_status',(SELECT search_status FROM selected),
    'search_completed_at',(SELECT search_completed_at FROM selected),
    'covered_through_at',(SELECT min(s.source_window_latest_at) FROM public.linkedin_discovery_cycle_scopes s
                          JOIN selected ON s.discovery_cycle_id=selected.id WHERE selected.search_status='sealed'),
    'predecessor_ids',COALESCE((SELECT jsonb_agg(id ORDER BY id) FROM predecessors),'[]'),
    'coverage_debt_count',(SELECT count(*) FROM debt),
    'expired_debt_count',(SELECT count(*) FROM debt WHERE status='expired_unresolved'),
    'requirement_count',(SELECT count(*) FROM blockers),
    'distinct_task_count',(SELECT count(DISTINCT task_id) FROM blockers),
    'task_examples',COALESCE((SELECT jsonb_agg(to_jsonb(b)) FROM
                     (SELECT * FROM blockers ORDER BY discovery_cycle_id,task_id,ingestion_run_id LIMIT 10)b),'[]'),
    'actionable_tasks',public.linkedin_actionable_task_count(),
    'leased_tasks',(SELECT count(*) FROM public.linkedin_discovery_tasks WHERE status='leased'),
    'publication',(SELECT to_jsonb(p) FROM public.freehire_publication_state p WHERE id=1),
    'source_policy',(SELECT to_jsonb(p) FROM public.linkedin_source_request_policy p WHERE source='linkedin'),
    'last_request_at',(SELECT max(started_at) FROM public.linkedin_source_request_grants),
    'classification',(SELECT jsonb_build_object(
        'pending',count(*) FILTER(WHERE freehire_compat_status='pending'),
        'processing',count(*) FILTER(WHERE freehire_compat_status='processing'),
        'failed',count(*) FILTER(WHERE freehire_compat_status='failed'),
        'oldest_pending_at',min(first_seen_at) FILTER(WHERE freehire_compat_status='pending'),
        'oldest_claim_at',min(freehire_compat_claimed_at) FILTER(WHERE freehire_compat_status='processing')
    ) FROM public.jobs WHERE provider='linkedin')
);
$$;
REVOKE ALL ON FUNCTION public.linkedin_publication_diagnostics(bigint) FROM PUBLIC;
DO $$
DECLARE table_name text;
BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='job_runner') THEN
        IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='jobs_o_linkedin_publication_diagnostics') THEN
            CREATE ROLE jobs_o_linkedin_publication_diagnostics NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='jobs_o_linkedin_publication_diagnostics'
                  AND (rolcanlogin OR rolsuper OR rolbypassrls)) THEN
            RAISE EXCEPTION 'unsafe diagnostic owner';
        END IF;
        GRANT USAGE ON SCHEMA public TO jobs_o_linkedin_publication_diagnostics;
        FOREACH table_name IN ARRAY ARRAY['linkedin_discovery_cycles','linkedin_discovery_cycle_scopes',
            'linkedin_discovery_cycle_resolutions','linkedin_coverage_debt','linkedin_discovery_requirements',
            'linkedin_discovery_tasks','listing_states','linkedin_discovery_requirement_acceptances','freehire_publication_state',
            'jobs','linkedin_source_request_policy','linkedin_source_request_grants'] LOOP
            EXECUTE format('GRANT SELECT ON public.%I TO jobs_o_linkedin_publication_diagnostics',table_name);
            IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=table_name
                          AND policyname='publication_diagnostics_select') THEN
                EXECUTE format('CREATE POLICY publication_diagnostics_select ON public.%I FOR SELECT TO jobs_o_linkedin_publication_diagnostics USING(true)',table_name);
            END IF;
        END LOOP;
        GRANT EXECUTE ON FUNCTION public.linkedin_actionable_task_count() TO jobs_o_linkedin_publication_diagnostics;
        ALTER FUNCTION public.linkedin_publication_diagnostics(bigint) OWNER TO jobs_o_linkedin_publication_diagnostics;
        GRANT EXECUTE ON FUNCTION public.linkedin_publication_diagnostics(bigint) TO job_runner;
    END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        GRANT EXECUTE ON FUNCTION public.linkedin_publication_diagnostics(bigint) TO service_role;
    END IF;
END $$;
COMMIT;
