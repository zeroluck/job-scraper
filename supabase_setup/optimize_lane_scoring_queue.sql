BEGIN;

CREATE INDEX IF NOT EXISTS job_archetype_memberships_score_queue_idx
  ON public.job_archetype_memberships (archetype, first_matched_at, job_id)
  WHERE filter_status = 'included' AND match_score IS NULL;

DROP INDEX IF EXISTS public.job_archetype_memberships_score_claim_idx;

CREATE OR REPLACE FUNCTION public.get_lane_jobs_to_score(
  p_archetype text,
  p_limit integer,
  p_worker_id text,
  p_lease_seconds integer DEFAULT 900
)
RETURNS TABLE(
  job_id text,
  job_title text,
  company text,
  description text,
  level text,
  archetype text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_now timestamptz := pg_catalog.clock_timestamp();
BEGIN
  IF auth.role() <> 'service_role' THEN
    RAISE EXCEPTION 'service_role required' USING errcode = '42501';
  END IF;
  IF NULLIF(pg_catalog.btrim(p_worker_id), '') IS NULL THEN
    RAISE EXCEPTION 'p_worker_id is required';
  END IF;

  RETURN QUERY
  WITH candidates AS MATERIALIZED (
    SELECT m.job_id, m.archetype, m.first_matched_at
    FROM public.job_archetype_memberships AS m
    JOIN public.jobs AS j ON j.job_id = m.job_id
    WHERE m.archetype = p_archetype
      AND m.filter_status = 'included'
      AND m.match_score IS NULL
      AND j.is_active IS TRUE
      AND j.description IS NOT NULL
      AND (
        m.score_claimed_by IS NULL
        OR m.score_claim_expires_at IS NULL
        OR m.score_claim_expires_at <= v_now
      )
    ORDER BY m.first_matched_at ASC, m.job_id ASC
    LIMIT GREATEST(p_limit, 0)
    FOR UPDATE OF m SKIP LOCKED
  ), claimed AS (
    UPDATE public.job_archetype_memberships AS m
    SET score_claimed_by = p_worker_id,
        score_claim_expires_at = v_now + pg_catalog.make_interval(
          secs => LEAST(GREATEST(p_lease_seconds, 30), 3600)
        ),
        updated_at = v_now
    FROM candidates AS c
    WHERE (m.job_id, m.archetype) = (c.job_id, c.archetype)
    RETURNING m.job_id, m.archetype, m.first_matched_at
  )
  SELECT j.job_id, j.job_title, j.company, j.description, j.level, c.archetype
  FROM claimed AS c
  JOIN public.jobs AS j ON j.job_id = c.job_id
  ORDER BY c.first_matched_at ASC, c.job_id ASC;
END;
$$;

REVOKE ALL ON FUNCTION public.get_lane_jobs_to_score(text, integer, text, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_lane_jobs_to_score(text, integer, text, integer)
  TO service_role;

COMMIT;
