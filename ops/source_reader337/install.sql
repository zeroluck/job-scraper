-- REVIEW CANDIDATE ONLY. No issuer, app, publication or data changes.
-- Run psql -X -v ON_ERROR_STOP=1 as postgres only after independent review.
-- One-shot: existing role or policy is drift, not an idempotent repair target.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_advisory_xact_lock(337, 7301);
DO $guard$
DECLARE g record;
BEGIN
 IF current_user <> 'postgres' OR current_setting('server_version_num')::int / 10000 <> 17 THEN
  RAISE EXCEPTION 'source reader administrator/version mismatch'; END IF;
 IF current_database() <> 'jobs' OR (SELECT oid FROM pg_database WHERE datname=current_database()) <> 299919 OR (SELECT system_identifier::text FROM pg_control_system()) <> '7701229561420400865' THEN
  RAISE EXCEPTION 'source reader authority mismatch'; END IF;
 IF EXISTS (SELECT FROM pg_database WHERE oid=16388 AND datallowconn)
 OR EXISTS (SELECT FROM pg_stat_activity WHERE datid=16388) THEN
  RAISE EXCEPTION 'original database isolation drift'; END IF;
 IF EXISTS (SELECT FROM pg_roles WHERE rolname='freehire_source_reader')
 OR EXISTS (SELECT FROM pg_policy WHERE polname='freehire_source_reader_linkedin') THEN
  RAISE EXCEPTION 'source reader already exists'; END IF;
 SELECT * INTO STRICT g FROM pg_roles WHERE rolname='jobs_gateway';
 IF g.rolsuper OR g.rolinherit OR g.rolcreatedb OR g.rolcreaterole OR g.rolreplication OR g.rolbypassrls
 OR NOT g.rolcanlogin OR g.rolconfig IS NOT NULL
 OR EXISTS (SELECT FROM pg_db_role_setting WHERE setrole=g.oid)
 OR EXISTS (SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid WHERE m.member=g.oid
  AND (r.rolname NOT IN ('job_runner','job_web','freehire_publication_reader','anon') OR m.admin_option OR m.inherit_option OR NOT m.set_option)) THEN
  RAISE EXCEPTION 'gateway authority drift'; END IF;
 IF NOT (SELECT relrowsecurity AND relowner='postgres'::regrole FROM pg_class WHERE oid='public.jobs'::regclass)
 OR EXISTS (SELECT FROM pg_policy WHERE polrelid='public.jobs'::regclass AND 0=ANY(polroles)) THEN
  RAISE EXCEPTION 'jobs RLS/owner drift'; END IF;
 IF md5(pg_get_functiondef('auth.require_jwt_claims()'::regprocedure)) <> '364fe8dd0062f20134add3a4efc25757'
 OR (SELECT prosecdef OR proowner <> 'postgres'::regrole FROM pg_proc WHERE oid='auth.require_jwt_claims()'::regprocedure) THEN
  RAISE EXCEPTION 'JWT hook drift'; END IF;
 -- PUBLIC capabilities cannot be negated by role-local REVOKE. Reject, never repair.
 IF EXISTS (SELECT FROM pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
  WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND a.grantee=0 AND a.privilege_type='CREATE')
 OR EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,c.relowner))) a
  WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND a.grantee=0)
 OR EXISTS (SELECT FROM pg_attribute c JOIN pg_class t ON t.oid=c.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
  CROSS JOIN LATERAL aclexplode(c.attacl) a WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND a.grantee=0)
 OR EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
  WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND a.grantee=0)
 OR EXISTS (SELECT FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a WHERE a.grantee=0)
 -- An absent global entry means PostgreSQL's implicit PUBLIC EXECUTE, not
 -- an empty ACL. Check each possible creator's own defaults: inherited role
 -- defaults do not apply to objects it creates. Include database CREATE, which
 -- permits creating new schemas. pg_database_owner cannot be an actual creator
 -- (SET ROLE is prohibited); its implicit member, the database owner, is checked.
 OR EXISTS (SELECT FROM pg_roles r
  CROSS JOIN LATERAL aclexplode(coalesce((SELECT d.defaclacl FROM pg_default_acl d
   WHERE d.defaclrole=r.oid AND d.defaclnamespace=0 AND d.defaclobjtype='f'),acldefault('f',r.oid))) a
  WHERE r.rolname <> 'pg_database_owner' AND a.grantee=0 AND a.privilege_type='EXECUTE'
   AND (has_database_privilege(r.oid,current_database(),'CREATE')
    OR EXISTS (SELECT FROM pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
     AND has_schema_privilege(r.oid,n.oid,'CREATE')))) THEN
  RAISE EXCEPTION 'PUBLIC/default ACL drift'; END IF;
END $guard$;
LOCK TABLE public.jobs IN ACCESS SHARE MODE;
CREATE ROLE freehire_source_reader NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public, auth TO freehire_source_reader;
GRANT EXECUTE ON FUNCTION auth.require_jwt_claims() TO freehire_source_reader;
GRANT SELECT (job_id, latest_job_id, company, job_title, location, description,
 posted_at, is_remote, freehire_category, freehire_seniority, salary_min,
 salary_max, salary_currency, description_fingerprint, provider)
 ON public.jobs TO freehire_source_reader;
CREATE POLICY freehire_source_reader_linkedin ON public.jobs
 FOR SELECT TO freehire_source_reader USING (provider = 'linkedin');
GRANT freehire_source_reader TO jobs_gateway WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
COMMENT ON ROLE freehire_source_reader IS 'source-reader337-v1: LinkedIn-only original importer reads; no writer/publication authority';
COMMIT;
