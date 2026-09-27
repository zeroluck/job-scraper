BEGIN;

-- Remove orphaned ResumeMuncher routines. Their backing tables no longer exist.
DROP FUNCTION IF EXISTS public.rmc_reset_database();
DROP FUNCTION IF EXISTS public.rmc_append_skill_source(text, uuid);

-- Location lookup tables are internal inputs to service-role location helpers.
ALTER TABLE public.metro_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.place_province_hints ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
  public.metro_aliases,
  public.place_province_hints
FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE
  public.metro_aliases,
  public.place_province_hints
TO service_role;

-- These application tables are server-only. RLS already denies API roles;
-- remove stale grants as defense in depth.
REVOKE ALL ON TABLE
  public.base_resume,
  public.census_population_2021,
  public.customized_resumes,
  public.job_keyword_insights,
  public.job_listing_archive,
  public.job_resume_links,
  public.jobs,
  public.keyword_insights
FROM PUBLIC, anon, authenticated;

-- Application migrations run as postgres. Future objects must opt into Data API
-- access explicitly instead of inheriting broad API-role privileges.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
