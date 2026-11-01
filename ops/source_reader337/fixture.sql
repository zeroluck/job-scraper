-- Synthetic fixture only: production column names/types and exact captured hook.
CREATE ROLE jobs_gateway LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE anon NOLOGIN;
CREATE ROLE job_runner NOLOGIN;
CREATE ROLE freehire_publication_reader NOLOGIN;
GRANT freehire_publication_reader TO jobs_gateway WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT anon TO jobs_gateway WITH INHERIT FALSE;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA auth;
REVOKE ALL ON SCHEMA auth FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE public.jobs (
"job_id" text,
"company" text,
"job_title" text,
"level" text,
"location" text,
"description" text,
"status" text,
"is_active" boolean,
"application_date" timestamp with time zone,
"resume_score" smallint,
"notes" text,
"scraped_at" timestamp with time zone,
"last_checked" timestamp with time zone,
"job_state" text,
"resume_score_stage" text,
"is_interested" boolean,
"customized_resume_id" uuid,
"provider" text,
"posted_at" timestamp with time zone,
"is_filtered" boolean,
"filter_reason" text,
"is_entry_level_filtered" boolean,
"insights_analyzed_at" timestamp with time zone,
"insights_reanalyzed_at" timestamp with time zone,
"search_query" text,
"archetype" text,
"filter_profile" text,
"canonical_key" text,
"original_job_id" text,
"latest_job_id" text,
"last_seen_posted_at" timestamp with time zone,
"posted_relative_text" text,
"applicant_count" integer,
"salary_text" text,
"salary_min" numeric,
"salary_max" numeric,
"salary_currency" text,
"recruiter_name" text,
"recruiter_profile_url" text,
"recruiter_identifier" text,
"description_fingerprint" text,
"first_seen_at" timestamp with time zone,
"last_seen_at" timestamp with time zone,
"seen_count" integer,
"repost_count" integer,
"listing_instances" jsonb,
"applicant_count_text" text,
"applicant_count_type" text,
"detail_metadata_checked_at" timestamp with time zone,
"location_province_code" text,
"location_scope" text,
"location_metro" text,
"posting_wave_count" integer,
"same_id_relist_count" integer,
"freehire_category" text,
"freehire_seniority" text,
"is_remote" boolean,
"freehire_remote_evidence" jsonb,
"freehire_compat_status" text,
"freehire_compat_input_hash" text,
"freehire_compat_import_hash" text,
"freehire_compat_model" text,
"freehire_compat_prompt_version" text,
"freehire_compat_schema_version" text,
"freehire_compat_confidence" numeric,
"freehire_compat_classified_at" timestamp with time zone,
"freehire_compat_error" text,
"freehire_compat_attempts" integer,
"freehire_compat_claimed_at" timestamp with time zone,
"freehire_compat_claimed_by" text,
"freehire_compat_provenance" jsonb,
"freehire_compat_next_retry_at" timestamp with time zone,
"listing_location_province_codes" text[],
"listing_location_scopes" text[],
"effective_posted_at" timestamp with time zone,
"canonical_revision" bigint);
ALTER TABLE public.jobs ADD PRIMARY KEY (job_id);
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE FUNCTION auth.require_jwt_claims()
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE c jsonb; expected_aud text; expected_iss text;
BEGIN
 expected_aud := nullif(current_setting('app.settings.jwt_expected_aud',true),'');
 expected_iss := nullif(current_setting('app.settings.jwt_expected_iss',true),'');
 c := coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb;
 IF expected_aud IS NULL OR expected_iss IS NULL
   OR jsonb_typeof(c->'exp') IS DISTINCT FROM 'number'
   OR jsonb_typeof(c->'aud') IS DISTINCT FROM 'string'
   OR jsonb_typeof(c->'iss') IS DISTINCT FROM 'string'
   OR c->>'aud' IS DISTINCT FROM expected_aud OR c->>'iss' IS DISTINCT FROM expected_iss
 THEN RAISE SQLSTATE 'PT401' USING MESSAGE='required JWT claims invalid'; END IF;
 IF (c->>'exp')::numeric <= extract(epoch FROM clock_timestamp())
   OR (c->>'exp') IN ('NaN','Infinity','-Infinity')
 THEN RAISE SQLSTATE 'PT401' USING MESSAGE='JWT expiry invalid'; END IF;
END $function$
;
REVOKE ALL ON FUNCTION auth.require_jwt_claims() FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO freehire_publication_reader;
CREATE FUNCTION public.get_freehire_publication_state() RETURNS int LANGUAGE sql AS $$ SELECT 123 $$;
GRANT EXECUTE ON FUNCTION public.get_freehire_publication_state() TO freehire_publication_reader;
CREATE TABLE public.other_data (secret text);
INSERT INTO public.other_data VALUES ('private');
CREATE FUNCTION public.forbidden_rpc() RETURNS text LANGUAGE sql SECURITY DEFINER AS $$ SELECT secret FROM public.other_data LIMIT 1 $$;
INSERT INTO public.jobs(job_id,latest_job_id,company,job_title,location,description,posted_at,is_remote,freehire_category,freehire_seniority,salary_min,salary_max,salary_currency,description_fingerprint,provider,freehire_compat_status,notes)
SELECT CASE WHEN i=1201 THEN '2' WHEN i=1202 THEN '10' WHEN i=1203 THEN '9' ELSE lpad(i::text,10,'0') END, CASE WHEN i%7=0 THEN NULL ELSE (i+2000)::text END,
CASE WHEN i%5=0 THEN NULL ELSE 'Acme – é '||i END,'Engineer '||i,
CASE WHEN i%3=0 THEN '' ELSE 'Toronto' END, E'<p>hello\n世界</p> '||i,
CASE WHEN i%9=0 THEN NULL ELSE '2026-01-01 12:34:56.123456+00'::timestamptz END,
CASE WHEN i%4=0 THEN NULL ELSE i%2=0 END,
CASE WHEN i<=12 THEN NULL ELSE 'Engineering' END,
CASE WHEN i%8=0 THEN NULL ELSE 'Senior' END,
CASE WHEN i%6=0 THEN NULL ELSE 12345.67+i END,
CASE WHEN i%6=0 THEN NULL ELSE 98765.43+i END,
CASE WHEN i%6=0 THEN NULL ELSE 'CAD' END,md5(i::text),'linkedin',
CASE WHEN i<=12 THEN 'failed' ELSE 'current' END,'private'
FROM generate_series(1,1203)i;
INSERT INTO public.jobs(job_id,provider,company) VALUES ('9999999998','indeed','excluded'),('9999999997','LinkedIn','excluded'),('9999999996',NULL,'excluded');
