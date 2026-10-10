-- Reconcile Oct-4 keyword/title insight drift: pin live definitions as baseline.
--
-- Remote applied-history contains five Oct-4 migrations with no repo file:
--   20261004202518 normalize_keyword_insight_case
--   20261004202859 optimize_case_insensitive_keyword_aggregation
--   20261004203719 preserve_canonical_keyword_display_labels
--   20261004203900 stabilize_keyword_label_query_plan
--   20261004204131 index_and_bound_keyword_label_resolution
-- plus older title-insight rewrites (tmp_bisect_a/b/c and follow-ups, history
-- only). The bodies below were snapshotted from prod via pg_get_functiondef /
-- pg_get_indexdef on 2026-10-10 and are reproduced verbatim (formatting only),
-- so applying this file is a provable no-op. Pre-apply normalized hashes
-- (md5 of lowercased whitespace-stripped pg_get_functiondef / pg_get_indexdef):
--   get_filtered_keyword_insights            a5be7fa22933e0c92604a99d0fe204ff
--   get_keyword_job_ids                      b5ab4f650ceb9af911477e9c3c9936a0
--   get_title_insights                       e83662b89e599a79740a49ce35f69734
--   get_title_job_ids                        e72e4c9641698fc76a25a70dd7adb961
--   idx_job_keyword_insights_keyword_key_category_job   2426cc5d1247508c0a2df847cb5826c9
--   idx_keyword_insights_keyword_key_category_label     ac3e82af2a390b6dd5a468ec07d59f1b
--
-- Per-object verdicts (live vs newest versioned file):
--   get_filtered_keyword_insights: PARITY with the qualify-jobs-first shape
--     (qualified_jobs as materialized, hash-join to job_keyword_insights,
--     canonical display-label CTEs). Baseline pin only.
--   get_keyword_job_ids: REAL DELTA. Live folds case at match time
--     (lower(btrim(jki.keyword)) = lower(btrim(p_keyword))); every versioned
--     file uses exact `jki.keyword = p_keyword`. Pinned live.
--   get_title_insights: REAL DELTA. Live selects `r.total as count` (matching
--     the outer `t.count` reference); the versioned file has
--     `r.total as title_count`, which leaves `t.count` unresolvable, plus an
--     older planner comment. Pinned live.
--   get_title_job_ids: PARITY (same case-folded title match, same
--     ranked/page/metadata pagination). Baseline pin only.
--   Both Oct-4 expression indexes: PARITY with the versioned statements.
--     Baseline pin only.
--   Grants on all four RPCs: deny-by-default (no anon/authenticated/public
--     execute), service_role only. Settings: work_mem + force_custom_plan on
--     the aggregate, force_custom_plan + enable_nestloop=off on title
--     insights. Re-asserted below.
--
-- Rule: all DDL via repo migration files; statements idempotent-only
-- (CREATE OR REPLACE, CREATE INDEX IF NOT EXISTS, unconditional
-- REVOKE/GRANT). Apply with `supabase db push` so stamps match, or MCP apply
-- + immediate commit using the RETURNED stamp.

create index if not exists idx_job_keyword_insights_keyword_key_category_job
  on public.job_keyword_insights (lower(btrim(keyword)), category, job_id);

create index if not exists idx_keyword_insights_keyword_key_category_label
  on public.keyword_insights (lower(btrim(keyword)), category, keyword)
  include (count);

create or replace function public.get_filtered_keyword_insights(
  p_providers text[] default null, p_archetypes text[] default null, p_levels text[] default null,
  p_filter_status text default null, p_companies text[] default null, p_job_titles text[] default null,
  p_provinces text[] default null, p_location_scopes text[] default null, p_exclude_metros text[] default null,
  p_category text default null, p_min_count integer default 2, p_limit integer default 1000, p_offset integer default 0
) returns table(keyword text, category text, count bigint, total_count bigint, last_updated timestamptz)
language sql stable security invoker set search_path = '' as $$
  with qualified_jobs as materialized (
    select j.job_id
    from public.jobs j
    where j.is_active is true
      and (p_providers is null or j.provider = any(p_providers))
      and (p_levels is null or j.level = any(p_levels))
      and (p_companies is null or j.company = any(p_companies))
      and (p_job_titles is null or j.job_title = any(p_job_titles))
      and (p_provinces is null or p_location_scopes is null or ('country' = any(p_location_scopes) and ('country' = j.location_scope or array['country'] && j.listing_location_scopes)) or (j.location_province_code = any(p_provinces) and j.location_scope = any(p_location_scopes)) or (p_provinces && j.listing_location_province_codes and p_location_scopes && j.listing_location_scopes))
      and (p_provinces is null or p_location_scopes is not null or j.location_province_code = any(p_provinces) or p_provinces && j.listing_location_province_codes)
      and (p_location_scopes is null or p_provinces is not null or j.location_scope = any(p_location_scopes) or p_location_scopes && j.listing_location_scopes)
      and (p_exclude_metros is null or j.location_metro is null or not (j.location_metro = any(p_exclude_metros)))
      and (p_archetypes is null or exists (
        select 1 from public.job_archetype_memberships m
        where m.job_id = j.job_id
          and (m.archetype = any(p_archetypes)
            or ('software_tpm' = any(p_archetypes) and m.archetype = 'technology_delivery'))
          and (p_filter_status = 'all'
            or (p_filter_status = 'filtered' and m.is_filtered is true)
            or (p_filter_status = 'unfiltered' and m.is_filtered is false)
            or (p_filter_status = 'entry_level' and m.is_filtered is true
              and m.filter_reason like 'title_entry_level:%'))))
      and (p_archetypes is not null or p_filter_status is null or p_filter_status = 'all'
        or (p_filter_status = 'filtered' and j.is_filtered is true)
        or (p_filter_status = 'unfiltered' and coalesce(j.is_filtered,false) is false)
        or (p_filter_status = 'entry_level' and j.is_entry_level_filtered is true))
  ), aggregated as (
    select lower(btrim(jki.keyword)) as keyword_key,
      min(btrim(jki.keyword)) as fallback_keyword, jki.category,
      count(distinct jki.job_id)::bigint as insight_count,
      max(jki.analyzed_at) as last_updated
    from public.job_keyword_insights jki
    join qualified_jobs q on q.job_id = jki.job_id
    where btrim(jki.keyword) <> ''
      and (p_category is null or jki.category = p_category)
      and (p_archetypes is null or (jki.archetype = any(p_archetypes) and exists (
        select 1 from public.job_archetype_memberships m
        where m.job_id = jki.job_id
          and m.archetype = case when jki.archetype = 'software_tpm' then 'technology_delivery' else jki.archetype end
          and (p_filter_status = 'all'
            or (p_filter_status = 'filtered' and m.is_filtered is true)
            or (p_filter_status = 'unfiltered' and m.is_filtered is false)
            or (p_filter_status = 'entry_level' and m.is_filtered is true
              and m.filter_reason like 'title_entry_level:%')))))
    group by lower(btrim(jki.keyword)), jki.category
    having count(distinct jki.job_id) >= greatest(p_min_count,0)
  ), ranked as (
    select a.*, count(*) over()::bigint total_count from aggregated a
  ), page as (
    select r.* from ranked r
    order by r.insight_count desc, r.keyword_key asc
    limit greatest(p_limit,0) offset greatest(p_offset,0)
  ), label_counts as (
    select p.keyword_key, ki.category, btrim(ki.keyword) as keyword,
      sum(ki.count)::bigint as label_count
    from public.keyword_insights ki
    join page p
      on p.keyword_key = lower(btrim(ki.keyword))
      and p.category = ki.category
    group by p.keyword_key, ki.category, btrim(ki.keyword)
  ), display_labels as (
    select distinct on (lc.keyword_key, lc.category)
      lc.keyword_key, lc.category, lc.keyword
    from label_counts lc
    order by lc.keyword_key, lc.category, lc.label_count desc, lc.keyword asc
  )
  select coalesce(dl.keyword, p.fallback_keyword) as keyword,
    p.category, p.insight_count as count, p.total_count, p.last_updated
  from page p
    left join display_labels dl
      on dl.keyword_key = p.keyword_key and dl.category = p.category
  order by p.insight_count desc, keyword asc;
$$;

revoke all on function public.get_filtered_keyword_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer,integer) from public, anon, authenticated;
grant execute on function public.get_filtered_keyword_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer,integer) to service_role;
alter function public.get_filtered_keyword_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer,integer) set work_mem = '256MB';
alter function public.get_filtered_keyword_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer,integer) set plan_cache_mode = force_custom_plan;

create or replace function public.get_keyword_job_ids(
  p_providers text[] default null, p_archetypes text[] default null, p_levels text[] default null,
  p_filter_status text default null, p_companies text[] default null, p_job_titles text[] default null,
  p_provinces text[] default null, p_location_scopes text[] default null, p_exclude_metros text[] default null,
  p_category text default null, p_keyword text default null,
  p_limit integer default 25, p_offset integer default 0
) returns table(job_id text, total_count bigint)
language sql stable security invoker set search_path = '' as $$
  with matching as (
    select distinct j.job_id, j.effective_posted_at
    from public.job_keyword_insights jki join public.jobs j on j.job_id = jki.job_id
    where j.is_active is true
      and p_keyword is not null
      and lower(btrim(jki.keyword)) = lower(btrim(p_keyword))
      and (p_category is null or jki.category = p_category)
      and (p_providers is null or j.provider = any(p_providers))
      and (p_archetypes is null or (jki.archetype = any(p_archetypes) and exists (
        select 1 from public.job_archetype_memberships m
        where m.job_id = j.job_id
          and m.archetype = case when jki.archetype = 'software_tpm' then 'technology_delivery' else jki.archetype end
          and (p_filter_status = 'all'
            or (p_filter_status = 'filtered' and m.is_filtered is true)
            or (p_filter_status = 'unfiltered' and m.is_filtered is false)
            or (p_filter_status = 'entry_level' and m.is_filtered is true
              and m.filter_reason like 'title_entry_level:%')))))
      and (p_archetypes is not null or p_filter_status is null or p_filter_status = 'all'
        or (p_filter_status = 'filtered' and j.is_filtered is true)
        or (p_filter_status = 'unfiltered' and coalesce(j.is_filtered,false) is false)
        or (p_filter_status = 'entry_level' and j.is_entry_level_filtered is true))
      and (p_levels is null or j.level = any(p_levels)) and (p_companies is null or j.company = any(p_companies))
      and (p_job_titles is null or j.job_title = any(p_job_titles))
      and (p_provinces is null or p_location_scopes is null or ('country' = any(p_location_scopes) and ('country' = j.location_scope or array['country'] && j.listing_location_scopes)) or (j.location_province_code = any(p_provinces) and j.location_scope = any(p_location_scopes)) or (p_provinces && j.listing_location_province_codes and p_location_scopes && j.listing_location_scopes))
      and (p_provinces is null or p_location_scopes is not null or j.location_province_code = any(p_provinces) or p_provinces && j.listing_location_province_codes)
      and (p_location_scopes is null or p_provinces is not null or j.location_scope = any(p_location_scopes) or p_location_scopes && j.listing_location_scopes)
      and (p_exclude_metros is null or j.location_metro is null or not (j.location_metro = any(p_exclude_metros)))
  ), ranked as (
    select m.*, count(*) over()::bigint total_count,
      row_number() over (order by m.effective_posted_at desc nulls last, m.job_id asc) ordinal
    from matching m
  ), page as (
    select r.job_id, r.total_count, r.ordinal from ranked r
    where r.ordinal > greatest(p_offset,0)
      and r.ordinal <= greatest(p_offset,0) + least(greatest(p_limit,0),100)
  ), metadata as (
    select count(*)::bigint total_count from matching
  )
  select result.job_id, result.total_count from (
    select p.job_id, p.total_count, p.ordinal from page p
    union all
    select null::text, m.total_count, null::bigint from metadata m
    where not exists (select 1 from page)
  ) result
  order by result.ordinal nulls last;
$$;

revoke all on function public.get_keyword_job_ids(text[],text[],text[],text,text[],text[],text[],text[],text[],text,text,integer,integer) from public, anon, authenticated;
grant execute on function public.get_keyword_job_ids(text[],text[],text[],text,text[],text[],text[],text[],text[],text,text,integer,integer) to service_role;

create or replace function public.get_title_insights(
  p_providers text[] default null, p_archetypes text[] default null, p_levels text[] default null,
  p_filter_status text default null, p_companies text[] default null, p_job_titles text[] default null,
  p_provinces text[] default null, p_location_scopes text[] default null, p_exclude_metros text[] default null,
  p_min_count integer default 2, p_limit integer default 250, p_offset integer default 0
) returns table(label text, count bigint, total_count bigint, last_updated timestamp with time zone)
language sql stable security invoker set search_path = '' as $$
  with scoped as (
    select j.job_id, j.job_title, j.last_seen_at,
      lower(btrim(j.job_title)) as norm
    from public.jobs j
    where j.is_active is true
      and j.job_title is not null and btrim(j.job_title) <> ''
      and (p_providers is null or j.provider = any(p_providers))
      and (p_archetypes is null or exists (
        select 1 from public.job_archetype_memberships m
        where m.job_id = j.job_id
          and m.archetype = any(p_archetypes)
          and (p_filter_status = 'all'
            or (p_filter_status = 'filtered' and m.is_filtered is true)
            or (p_filter_status = 'unfiltered' and m.is_filtered is false)
            or (p_filter_status = 'entry_level' and m.is_filtered is true
              and m.filter_reason like 'title_entry_level:%'))))
      and (p_archetypes is not null or p_filter_status is null or p_filter_status = 'all'
        or (p_filter_status = 'filtered' and j.is_filtered is true)
        or (p_filter_status = 'unfiltered' and coalesce(j.is_filtered,false) is false)
        or (p_filter_status = 'entry_level' and j.is_entry_level_filtered is true))
      and (p_levels is null or j.level = any(p_levels)) and (p_companies is null or j.company = any(p_companies))
      and (p_job_titles is null or j.job_title = any(p_job_titles))
      and (p_provinces is null or p_location_scopes is null or ('country' = any(p_location_scopes) and ('country' = j.location_scope or array['country'] && j.listing_location_scopes)) or (j.location_province_code = any(p_provinces) and j.location_scope = any(p_location_scopes)) or (p_provinces && j.listing_location_province_codes and p_location_scopes && j.listing_location_scopes))
      and (p_provinces is null or p_location_scopes is not null or j.location_province_code = any(p_provinces) or p_provinces && j.listing_location_province_codes)
      and (p_location_scopes is null or p_provinces is not null or j.location_scope = any(p_location_scopes) or p_location_scopes && j.listing_location_scopes)
      and (p_exclude_metros is null or j.location_metro is null or not (j.location_metro = any(p_exclude_metros)))
  ), grouped as (
    select s.norm, s.job_title as display, count(*)::bigint as c,
      max(s.last_seen_at) as lu
    from scoped s
    group by s.norm, s.job_title
  ), ranked as (
    -- One pass over the spellings: most frequent original wins the label,
    -- no self-join (which planned pathologically under generic params).
    select g.norm, g.display,
      sum(g.c) over (partition by g.norm)::bigint as total,
      row_number() over (partition by g.norm order by g.c desc, g.display asc) as rn,
      max(g.lu) over (partition by g.norm) as norm_lu
    from grouped g
  ), aggregated as (
    select r.display as label, r.total as count, r.norm_lu as last_updated
    from ranked r
    where r.rn = 1 and r.total >= greatest(p_min_count, 0)
  ), totals as (
    select a.*, count(*) over()::bigint total_count from aggregated a
  )
  select t.label, t.count, t.total_count, t.last_updated from totals t
  order by t.count desc, t.label asc
  limit greatest(p_limit,0) offset greatest(p_offset,0);
$$;

revoke all on function public.get_title_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],integer,integer,integer) from public, anon, authenticated;
grant execute on function public.get_title_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],integer,integer,integer) to service_role;
alter function public.get_title_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],integer,integer,integer) set plan_cache_mode = force_custom_plan;
alter function public.get_title_insights(text[],text[],text[],text,text[],text[],text[],text[],text[],integer,integer,integer) set enable_nestloop = off;

create or replace function public.get_title_job_ids(
  p_providers text[] default null, p_archetypes text[] default null, p_levels text[] default null,
  p_filter_status text default null, p_companies text[] default null, p_job_titles text[] default null,
  p_provinces text[] default null, p_location_scopes text[] default null, p_exclude_metros text[] default null,
  p_title text default '',
  p_limit integer default 25, p_offset integer default 0
) returns table(job_id text, total_count bigint)
language sql stable security invoker set search_path = '' as $$
  with matching as (
    select distinct j.job_id, j.effective_posted_at
    from public.jobs j
    where j.is_active is true
      and j.job_title is not null
      and lower(btrim(j.job_title)) = lower(btrim(p_title))
      and (p_providers is null or j.provider = any(p_providers))
      and (p_archetypes is null or exists (
        select 1 from public.job_archetype_memberships m
        where m.job_id = j.job_id
          and m.archetype = any(p_archetypes)
          and (p_filter_status = 'all'
            or (p_filter_status = 'filtered' and m.is_filtered is true)
            or (p_filter_status = 'unfiltered' and m.is_filtered is false)
            or (p_filter_status = 'entry_level' and m.is_filtered is true
              and m.filter_reason like 'title_entry_level:%'))))
      and (p_archetypes is not null or p_filter_status is null or p_filter_status = 'all'
        or (p_filter_status = 'filtered' and j.is_filtered is true)
        or (p_filter_status = 'unfiltered' and coalesce(j.is_filtered,false) is false)
        or (p_filter_status = 'entry_level' and j.is_entry_level_filtered is true))
      and (p_levels is null or j.level = any(p_levels)) and (p_companies is null or j.company = any(p_companies))
      and (p_job_titles is null or j.job_title = any(p_job_titles))
      and (p_provinces is null or p_location_scopes is null or ('country' = any(p_location_scopes) and ('country' = j.location_scope or array['country'] && j.listing_location_scopes)) or (j.location_province_code = any(p_provinces) and j.location_scope = any(p_location_scopes)) or (p_provinces && j.listing_location_province_codes and p_location_scopes && j.listing_location_scopes))
      and (p_provinces is null or p_location_scopes is not null or j.location_province_code = any(p_provinces) or p_provinces && j.listing_location_province_codes)
      and (p_location_scopes is null or p_provinces is not null or j.location_scope = any(p_location_scopes) or p_location_scopes && j.listing_location_scopes)
      and (p_exclude_metros is null or j.location_metro is null or not (j.location_metro = any(p_exclude_metros)))
  ), ranked as (
    select m.*, count(*) over()::bigint total_count,
      row_number() over (order by m.effective_posted_at desc nulls last, m.job_id asc) ordinal
    from matching m
  ), page as (
    select r.job_id, r.total_count, r.ordinal from ranked r
    where r.ordinal > greatest(p_offset,0)
      and r.ordinal <= greatest(p_offset,0) + least(greatest(p_limit,0),100)
  ), metadata as (
    select count(*)::bigint total_count from matching
  )
  select result.job_id, result.total_count from (
    select p.job_id, p.total_count, p.ordinal from page p
    union all
    select null::text, m.total_count, null::bigint from metadata m
    where not exists (select 1 from page)
  ) result
  order by result.ordinal nulls last;
$$;

revoke all on function public.get_title_job_ids(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer) from public, anon, authenticated;
grant execute on function public.get_title_job_ids(text[],text[],text[],text,text[],text[],text[],text[],text[],text,integer,integer) to service_role;
