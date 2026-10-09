-- Honor declared expired coverage-debt windows in page containment checks.
--
-- After an outage gap longer than outage_recovery_cap_hours, scope manifests
-- cap the fetch window at the recovery cap and declare the beyond-cap slice
-- as expired_window_* coverage debt (recorded as expired_unresolved at scope
-- finish, never silently dropped). The client fetches from that declared
-- truncation point, so the commit and scope-finish containment checks must
-- accept pages covering the effective window
--   [COALESCE(expired_window_latest_at, source_window_earliest_at),
--    source_window_latest_at]
-- instead of the full persisted window. Without this, every post-gap run
-- hard-fails: first the fetch guard, then (after client-side clamping)
-- commit_linkedin_discovery_page / finish_linkedin_discovery_scope with
-- "page window does not contain manifest window".
--
-- Semantics are unchanged when no expired window is declared (COALESCE falls
-- back to source_window_earliest_at, byte-identical predicate).
--
-- Implemented as guarded in-place replacements of the live definitions so
-- ownership, grants, and function settings are preserved and the migration
-- fails loudly instead of silently no-op'ing on unexpected definitions.

DO $do$
DECLARE
    commit_def text;
    finish_def text;
BEGIN
    SELECT pg_catalog.pg_get_functiondef(oid) INTO commit_def
    FROM pg_catalog.pg_proc
    WHERE proname = 'commit_linkedin_discovery_page'
      AND pg_catalog.pg_get_functiondef(oid) LIKE '%page window does not contain manifest window%';
    IF commit_def IS NULL THEN
        RAISE EXCEPTION 'commit containment predicate not found' USING ERRCODE = '55000';
    END IF;
    commit_def := replace(commit_def,
        'IF (p_page->>''source_window_earliest_at'')::timestamptz > scope_row.source_window_earliest_at',
        'IF (p_page->>''source_window_earliest_at'')::timestamptz > COALESCE(scope_row.expired_window_latest_at, scope_row.source_window_earliest_at)');
    IF position('COALESCE(scope_row.expired_window_latest_at' IN commit_def) = 0 THEN
        RAISE EXCEPTION 'commit containment patch did not apply' USING ERRCODE = '55000';
    END IF;
    EXECUTE commit_def;

    SELECT pg_catalog.pg_get_functiondef(oid) INTO finish_def
    FROM pg_catalog.pg_proc
    WHERE proname = 'finish_linkedin_discovery_scope'
      AND pg_catalog.pg_get_functiondef(oid) LIKE '%incomplete durable page evidence%';
    IF finish_def IS NULL THEN
        RAISE EXCEPTION 'finish evidence predicate not found' USING ERRCODE = '55000';
    END IF;
    finish_def := replace(finish_def,
        'AND (page.source_window_earliest_at > scope_row.source_window_earliest_at',
        'AND (page.source_window_earliest_at > COALESCE(scope_row.expired_window_latest_at, scope_row.source_window_earliest_at)');
    IF position('COALESCE(scope_row.expired_window_latest_at' IN finish_def) = 0 THEN
        RAISE EXCEPTION 'finish evidence patch did not apply' USING ERRCODE = '55000';
    END IF;
    EXECUTE finish_def;
END $do$;
