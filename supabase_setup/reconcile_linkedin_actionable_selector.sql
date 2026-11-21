-- Authoritative copy; mirror into the companion web migration chain.
-- Reconcile the native 2026-11-03 fix without replaying consolidated SQL.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
DO $$
DECLARE
    definition text;
    owner_name text;
    marker text := 'AND cycle.canonical_status = ''pending''';
BEGIN
    SELECT pg_get_functiondef(oid),pg_get_userbyid(proowner) INTO definition,owner_name FROM pg_proc
    WHERE oid='public.get_resumable_linkedin_discovery_cycle(boolean,text[])'::regprocedure;
    IF position('task.attempt_count < task.max_attempts' IN definition)=0 THEN
        IF position(marker IN definition)=0 THEN RAISE EXCEPTION 'selector contract changed'; END IF;
        EXECUTE replace(definition,marker,marker || $predicate$
               AND EXISTS (
                   SELECT 1 FROM public.linkedin_discovery_tasks task
                   WHERE task.status = 'leased'
                      OR (task.status IN ('pending','failed_retryable') AND task.attempt_count < task.max_attempts)
               )$predicate$);
    END IF;
    IF owner_name LIKE 'jobs_o_%' THEN
        EXECUTE format('GRANT SELECT ON public.linkedin_discovery_tasks TO %I',owner_name);
        IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='linkedin_discovery_tasks'
                      AND policyname='selector_resume_tasks_select') THEN
            EXECUTE format('CREATE POLICY selector_resume_tasks_select ON public.linkedin_discovery_tasks FOR SELECT TO %I USING(true)',owner_name);
        END IF;
    END IF;
END;
$$;
COMMIT;
