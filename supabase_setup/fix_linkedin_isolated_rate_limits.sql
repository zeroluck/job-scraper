-- Authoritative copy; web holds the matching incremental history mirror.
-- A usable response ends the denial streak, independently of cautious pacing recovery.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
DO $$
DECLARE
    definition text;
    marker text := 'consecutive_429 = CASE WHEN successful_since_throttle >= 19 THEN 0 ELSE consecutive_429 END';
BEGIN
    SELECT pg_get_functiondef('public.finish_linkedin_request_feedback(uuid,text,text,integer,integer,jsonb,jsonb)'::regprocedure)
    INTO definition;
    IF position(marker IN definition)>0 THEN
        IF (length(definition)-length(replace(definition,marker,'')))/length(marker)<>1 THEN
            RAISE EXCEPTION 'ambiguous source feedback checkpoint';
        END IF;
        EXECUTE replace(definition,marker,'consecutive_429 = 0');
    ELSIF position('consecutive_429 = 0,' IN definition)=0 THEN
        RAISE EXCEPTION 'source feedback contract changed';
    END IF;
END;
$$;

-- Recompute the faulty derived streak from immutable outcome history. Preserve
-- every grant/attempt, current spacing, Retry-After cooldown, and circuit state.
UPDATE public.linkedin_source_request_policy policy
SET consecutive_429=(
    SELECT LEAST(1000,count(*))::integer
    FROM public.linkedin_source_request_grants g
    WHERE g.source=policy.source AND g.status='finished' AND g.http_status=429
      AND g.finished_at>COALESCE((
          SELECT max(success.finished_at) FROM public.linkedin_source_request_grants success
          WHERE success.source=policy.source AND success.status='finished'
            AND success.http_status BETWEEN 200 AND 299
      ),'-infinity'::timestamptz)
), updated_at=clock_timestamp()
WHERE policy.source='linkedin';
COMMIT;
