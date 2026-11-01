-- Explicit narrow rollback. No DROP OWNED, CASCADE or unrelated role repair.
-- Stop/quiesce any future consumer before rollback; none is activated by install.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_advisory_xact_lock(337, 7301);
DO $guard$
DECLARE r record;
BEGIN
 IF current_user <> 'postgres' OR current_setting('server_version_num')::int / 10000 <> 17 THEN
  RAISE EXCEPTION 'source reader administrator/version mismatch'; END IF;
 IF current_database() <> 'jobs' OR (SELECT oid FROM pg_database WHERE datname=current_database()) <> 299919 OR (SELECT system_identifier::text FROM pg_control_system()) <> '7701229561420400865' THEN
  RAISE EXCEPTION 'source reader authority mismatch'; END IF;
 SELECT * INTO STRICT r FROM pg_roles WHERE rolname='freehire_source_reader';
 IF r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls OR r.rolconfig IS NOT NULL
 OR shobj_description(r.oid,'pg_authid') IS DISTINCT FROM 'source-reader337-v1: LinkedIn-only original importer reads; no writer/publication authority'
 OR EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid OR (roleid=r.oid AND (member <> 'jobs_gateway'::regrole OR admin_option OR inherit_option OR NOT set_option))) THEN
  RAISE EXCEPTION 'source reader rollback drift'; END IF;
 IF NOT EXISTS (SELECT FROM pg_policy WHERE polrelid='public.jobs'::regclass AND polname='freehire_source_reader_linkedin'
  AND polcmd='r' AND polpermissive AND polroles=ARRAY[r.oid]
  AND pg_get_expr(polqual,polrelid)='(provider = ''linkedin''::text)' AND polwithcheck IS NULL) THEN
  RAISE EXCEPTION 'source reader rollback policy drift'; END IF;
END $guard$;
REVOKE freehire_source_reader FROM jobs_gateway;
DROP POLICY freehire_source_reader_linkedin ON public.jobs;
REVOKE SELECT (job_id, latest_job_id, company, job_title, location, description,
 posted_at, is_remote, freehire_category, freehire_seniority, salary_min,
 salary_max, salary_currency, description_fingerprint, provider)
 ON public.jobs FROM freehire_source_reader;
REVOKE EXECUTE ON FUNCTION auth.require_jwt_claims() FROM freehire_source_reader;
REVOKE USAGE ON SCHEMA public, auth FROM freehire_source_reader;
-- Unexpected dependencies make DROP fail and the entire transaction roll back.
DROP ROLE freehire_source_reader;
COMMIT;
