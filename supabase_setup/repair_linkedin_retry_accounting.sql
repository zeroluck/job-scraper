-- Authoritative copy; mirror into the companion web migration chain.
-- Charge a durable task attempt on its first source grant, not on local claim.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

CREATE OR REPLACE FUNCTION public.claim_linkedin_discovery_tasks(p_worker_id text, p_limit integer, p_order_mode text)
RETURNS SETOF public.linkedin_discovery_tasks
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF p_worker_id IS NULL OR btrim(p_worker_id) = '' OR p_limit IS NULL OR p_limit < 1 OR p_limit > 100
       OR p_order_mode IS NULL OR p_order_mode NOT IN ('oldest', 'newest') THEN
        RAISE EXCEPTION 'invalid task claim parameters' USING ERRCODE = '22023';
    END IF;
    UPDATE public.linkedin_discovery_tasks
    SET status = 'failed_terminal', completed_at = clock_timestamp(),
        last_error_code = COALESCE(last_error_code, 'lease_expired_attempts_exhausted'),
        leased_by = NULL, leased_at = NULL, lease_expires_at = NULL, lease_token = NULL
    WHERE status = 'leased' AND lease_expires_at <= clock_timestamp() AND attempt_count >= max_attempts;
    UPDATE public.linkedin_discovery_tasks SET status = 'failed_retryable', leased_by = NULL, leased_at = NULL,
        lease_expires_at = NULL, lease_token = NULL, available_at = clock_timestamp()
    WHERE status = 'leased' AND lease_expires_at <= clock_timestamp() AND attempt_count < max_attempts;
    RETURN QUERY WITH picked AS (
        SELECT task.id FROM public.linkedin_discovery_tasks task
        WHERE task.status IN ('pending', 'failed_retryable')
          AND task.attempt_count < task.max_attempts AND task.available_at <= clock_timestamp()
          AND (p_order_mode <> 'newest' OR (task.task_kind = 'initial_detail' AND task.requirement_key = 'first'))
        ORDER BY
          CASE WHEN p_order_mode = 'oldest' THEN COALESCE((
              SELECT min(cycle.discovery_sequence) FROM public.linkedin_discovery_requirements requirement
              JOIN public.linkedin_discovery_cycles cycle ON cycle.id = requirement.discovery_cycle_id
              WHERE requirement.task_id = task.id AND requirement.required
          ), 9223372036854775807) END,
          task.priority DESC,
          CASE WHEN p_order_mode = 'newest' THEN task.first_observed_at END DESC,
          task.first_observed_at, task.id
        FOR UPDATE OF task SKIP LOCKED LIMIT p_limit
    ) UPDATE public.linkedin_discovery_tasks task SET status = 'leased', leased_by = p_worker_id,
        leased_at = clock_timestamp(), lease_expires_at = clock_timestamp() + interval '10 minutes',
        lease_token = extensions.gen_random_uuid()
    FROM picked WHERE task.id = picked.id RETURNING task.*;
END;
$$;

-- The grant function is also changed by durable feedback. This narrow guarded
-- edit preserves its live body, ownership, ACL, and all native lease checks.
DO $$
DECLARE
    definition text;
    marker text := '    INSERT INTO public.linkedin_source_request_grants (';
    owner_name text;
    charge text := $charge$
    IF p_producer = 'adaptive-detail' THEN
        -- Policy lock serializes grants. Count once per lease, including retries.
        IF NOT EXISTS (
            SELECT 1 FROM public.linkedin_discovery_task_attempts
            WHERE task_id = split_part(p_request_key, ':', 2)::bigint
              AND lease_token = split_part(p_request_key, ':', 3)::uuid
        ) THEN
            UPDATE public.linkedin_discovery_tasks SET attempt_count = attempt_count + 1
            WHERE id = split_part(p_request_key, ':', 2)::bigint
              AND lease_token = split_part(p_request_key, ':', 3)::uuid
              AND status = 'leased' AND lease_expires_at > clock_timestamp()
              AND attempt_count < max_attempts;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'source attempt requires an eligible live lease' USING ERRCODE = '55000';
            END IF;
        END IF;
    END IF;
$charge$;
BEGIN
    SELECT pg_get_functiondef(oid), pg_get_userbyid(proowner) INTO definition, owner_name
    FROM pg_proc WHERE oid = 'public.acquire_linkedin_request_grant(text,text,text)'::regprocedure;
    IF position('source attempt requires an eligible live lease' IN definition) = 0 THEN
        IF (length(definition) - length(replace(definition, marker, ''))) / length(marker) <> 1
           OR position('adaptive detail request requires an active task lease' IN definition) = 0 THEN
            RAISE EXCEPTION 'request grant contract changed; retry-accounting migration rejected';
        END IF;
        EXECUTE replace(definition, marker, charge || marker);
    END IF;
    IF owner_name LIKE 'jobs_o_%' THEN
        EXECUTE format('GRANT UPDATE (attempt_count) ON public.linkedin_discovery_tasks TO %I', owner_name);
        EXECUTE format('GRANT SELECT ON public.linkedin_discovery_task_attempts TO %I', owner_name);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='linkedin_discovery_tasks'
                       AND policyname='source_attempt_charge') THEN
            EXECUTE format('CREATE POLICY source_attempt_charge ON public.linkedin_discovery_tasks FOR UPDATE TO %I USING (status = ''leased'') WITH CHECK (status = ''leased'')', owner_name);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='linkedin_discovery_task_attempts'
                       AND policyname='source_attempt_charge_select') THEN
            EXECUTE format('CREATE POLICY source_attempt_charge_select ON public.linkedin_discovery_task_attempts FOR SELECT TO %I USING (true)', owner_name);
        END IF;
    END IF;
END;
$$;
COMMIT;
