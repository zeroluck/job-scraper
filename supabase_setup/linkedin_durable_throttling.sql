-- Authoritative copy; mirror into the companion web migration chain.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.linkedin_source_request_policy
    ADD COLUMN IF NOT EXISTS cooldown_until timestamptz NOT NULL DEFAULT '-infinity',
    ADD COLUMN IF NOT EXISTS effective_interval_ms integer NOT NULL DEFAULT 5000 CHECK (effective_interval_ms BETWEEN 2500 AND 60000),
    ADD COLUMN IF NOT EXISTS consecutive_429 integer NOT NULL DEFAULT 0 CHECK (consecutive_429 >= 0),
    ADD COLUMN IF NOT EXISTS successful_since_throttle integer NOT NULL DEFAULT 0 CHECK (successful_since_throttle >= 0),
    ADD COLUMN IF NOT EXISTS last_429_at timestamptz;
ALTER TABLE public.linkedin_source_request_grants
    ADD COLUMN IF NOT EXISTS retry_after_seconds integer CHECK (retry_after_seconds BETWEEN 0 AND 604800),
    ADD COLUMN IF NOT EXISTS response_headers jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(response_headers) = 'object'),
    ADD COLUMN IF NOT EXISTS execution_metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(execution_metadata) = 'object');

CREATE OR REPLACE FUNCTION public.finish_linkedin_request_feedback(
    p_grant_id uuid, p_producer text, p_response_class text, p_http_status integer,
    p_retry_after_seconds integer, p_response_headers jsonb, p_execution_metadata jsonb
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    finished_grant public.linkedin_source_request_grants%ROWTYPE;
    policy public.linkedin_source_request_policy%ROWTYPE;
    finished timestamptz := clock_timestamp();
BEGIN
    IF p_retry_after_seconds < 0 OR p_retry_after_seconds > 604800
       OR jsonb_typeof(p_response_headers) IS DISTINCT FROM 'object'
       OR jsonb_typeof(p_execution_metadata) IS DISTINCT FROM 'object'
       OR octet_length(p_response_headers::text) > 4096 OR octet_length(p_execution_metadata::text) > 4096 THEN
        RAISE EXCEPTION 'invalid request feedback' USING ERRCODE = '22023';
    END IF;
    -- Same lock order as acquire/open-circuit: policy before grant/task rows.
    SELECT * INTO STRICT policy FROM public.linkedin_source_request_policy WHERE source = 'linkedin' FOR UPDATE;
    UPDATE public.linkedin_source_request_grants
    SET status = 'finished', finished_at = finished, response_class = p_response_class, http_status = p_http_status,
        retry_after_seconds = p_retry_after_seconds, response_headers = p_response_headers,
        execution_metadata = p_execution_metadata
    WHERE id = p_grant_id AND producer = p_producer AND status = 'consumed'
    RETURNING * INTO finished_grant;
    IF finished_grant.id IS NULL THEN RETURN false; END IF;
    IF p_producer = 'adaptive-detail' AND finished_grant.request_key ~ '^task:[0-9]+:[0-9a-f-]{36}:[^:]+:[0-9]+$' THEN
        INSERT INTO public.linkedin_discovery_task_attempts (
            task_id, lease_token, request_attempt, request_grant_id, response_class,
            http_status, parser_version, started_at, finished_at
        ) VALUES (
            split_part(finished_grant.request_key, ':', 2)::bigint,
            split_part(finished_grant.request_key, ':', 3)::uuid,
            split_part(finished_grant.request_key, ':', 5)::integer,
            finished_grant.id, p_response_class, p_http_status, 'linkedin-detail-v1', finished_grant.started_at, finished
        ) ON CONFLICT (request_grant_id) DO UPDATE SET response_class = EXCLUDED.response_class,
            http_status = EXCLUDED.http_status, parser_version = EXCLUDED.parser_version, finished_at = EXCLUDED.finished_at;
    END IF;
    IF p_http_status = 429 THEN
        UPDATE public.linkedin_source_request_policy
        SET effective_interval_ms = LEAST(60000, GREATEST(minimum_interval_ms, effective_interval_ms) * 2),
            consecutive_429 = LEAST(1000, consecutive_429 + 1), successful_since_throttle = 0,
            cooldown_until = GREATEST(cooldown_until, finished + make_interval(secs => GREATEST(
                COALESCE(p_retry_after_seconds, 0), LEAST(3600, 60 * power(2, LEAST(consecutive_429, 6)))
            ))), last_429_at = finished, updated_at = finished
        WHERE source = 'linkedin';
    ELSIF p_http_status BETWEEN 200 AND 299 THEN
        UPDATE public.linkedin_source_request_policy
        SET successful_since_throttle = CASE WHEN successful_since_throttle >= 19 THEN 0 ELSE successful_since_throttle + 1 END,
            effective_interval_ms = CASE WHEN successful_since_throttle >= 19
                THEN GREATEST(minimum_interval_ms, 5000, ceil(effective_interval_ms * 0.9)::integer)
                ELSE effective_interval_ms END,
            consecutive_429 = CASE WHEN successful_since_throttle >= 19 THEN 0 ELSE consecutive_429 END,
            updated_at = finished WHERE source = 'linkedin';
    END IF;
    -- Retry-After on e.g. 503 is also a shared source instruction.
    IF p_retry_after_seconds > 0 THEN
        UPDATE public.linkedin_source_request_policy
        SET cooldown_until = GREATEST(cooldown_until, finished + make_interval(secs => p_retry_after_seconds)),
            updated_at = finished WHERE source = 'linkedin';
    END IF;
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb) FROM PUBLIC;

-- Existing producers retain their four-argument contract and feed the same
-- policy even before upgrading their richer response telemetry.
CREATE OR REPLACE FUNCTION public.finish_linkedin_request_grant(
    p_grant_id uuid, p_producer text, p_response_class text, p_http_status integer
) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT public.finish_linkedin_request_feedback(p_grant_id,p_producer,p_response_class,p_http_status,NULL,'{}','{}');
$$;

DO $$
DECLARE
    definition text;
    marker text := '    IF v_now < policy.next_allowed_at THEN';
    owner_name text;
    command text;
BEGIN
    SELECT pg_get_functiondef(oid) INTO definition FROM pg_proc
    WHERE oid = 'public.acquire_linkedin_request_grant(text,text,text)'::regprocedure;
    IF position('policy.cooldown_until' IN definition) = 0 THEN
        IF position(marker IN definition) = 0 OR position('minimum_interval_ms / 1000.0' IN definition) = 0 THEN
            RAISE EXCEPTION 'request grant contract changed; cooldown migration rejected';
        END IF;
        definition := replace(definition, marker,
            '    policy.next_allowed_at := GREATEST(policy.next_allowed_at, policy.cooldown_until);' || chr(10) || marker);
        definition := replace(definition, 'minimum_interval_ms / 1000.0', 'GREATEST(minimum_interval_ms, effective_interval_ms) / 1000.0');
        -- Bound the wait integer even if an operator sets a very long cooldown.
        definition := replace(definition, 'pg_catalog.ceil(EXTRACT(EPOCH FROM (policy.next_allowed_at - v_now)) * 1000)::integer',
            'LEAST(60000, pg_catalog.ceil(EXTRACT(EPOCH FROM (policy.next_allowed_at - v_now)) * 1000))::integer');
        EXECUTE definition;
    END IF;
    SELECT pg_get_functiondef(oid) INTO definition FROM pg_proc
    WHERE oid = 'public.consume_linkedin_request_grant(uuid,text)'::regprocedure;
    IF position('policy.cooldown_until' IN definition) = 0 THEN
        IF position('IF grant_row.id IS NULL OR' IN definition) = 0 THEN
            RAISE EXCEPTION 'grant consumption contract changed; cooldown migration rejected';
        END IF;
        -- Adaptive detail now charges atomically at acquire; its retired pending
        -- grant path must reacquire rather than bypass the lease/attempt check.
        definition := replace(definition, 'IF grant_row.id IS NULL OR',
            'IF started < policy.cooldown_until OR p_producer = ''adaptive-detail'' OR grant_row.id IS NULL OR');
        definition := replace(definition, 'minimum_interval_ms / 1000.0',
            'GREATEST(minimum_interval_ms, effective_interval_ms) / 1000.0');
        EXECUTE definition;
    END IF;
    SELECT pg_get_userbyid(proowner) INTO owner_name FROM pg_proc
    WHERE oid = 'public.finish_linkedin_request_grant(uuid,text,text,integer)'::regprocedure;
    EXECUTE format('ALTER FUNCTION public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb) OWNER TO %I', owner_name);
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb) TO %I', owner_name);
    IF owner_name LIKE 'jobs_o_%' THEN
        EXECUTE format('GRANT SELECT, UPDATE ON public.linkedin_source_request_policy TO %I', owner_name);
        FOREACH command IN ARRAY ARRAY['SELECT','UPDATE'] LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='linkedin_source_request_policy'
                           AND policyname='feedback_policy_' || lower(command)) THEN
                EXECUTE format('CREATE POLICY %I ON public.linkedin_source_request_policy FOR %s TO %I USING (true)%s',
                    'feedback_policy_' || lower(command), command, owner_name,
                    CASE WHEN command='UPDATE' THEN ' WITH CHECK (true)' ELSE '' END);
            END IF;
        END LOOP;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='job_runner') THEN
        GRANT EXECUTE ON FUNCTION public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb) TO job_runner;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        GRANT EXECUTE ON FUNCTION public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb) TO service_role;
    END IF;
END;
$$;
COMMIT;
