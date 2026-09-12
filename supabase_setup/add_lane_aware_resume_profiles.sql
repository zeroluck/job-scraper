BEGIN;

CREATE OR REPLACE FUNCTION public.replace_base_resume(p_resume_data jsonb)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    target_id uuid;
BEGIN
    IF p_resume_data IS NULL
       OR pg_catalog.jsonb_typeof(p_resume_data) <> 'object'
       OR p_resume_data = '{}'::jsonb THEN
        RAISE EXCEPTION 'resume payload must be a non-empty JSON object';
    END IF;

    SELECT id INTO target_id
    FROM public.base_resume
    ORDER BY updated_at DESC
    LIMIT 1
    FOR UPDATE;

    IF target_id IS NULL THEN
        INSERT INTO public.base_resume (resume_data) VALUES (p_resume_data);
    ELSE
        UPDATE public.base_resume SET resume_data = p_resume_data WHERE id = target_id;
    END IF;

    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.replace_base_resume(jsonb)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_base_resume(jsonb)
TO service_role;

CREATE OR REPLACE FUNCTION public.replace_archetype_resume_profiles(p_profiles jsonb)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    target_base_resume_id uuid;
BEGIN
    IF p_profiles IS NULL
       OR pg_catalog.jsonb_typeof(p_profiles) <> 'object'
       OR p_profiles = '{}'::jsonb THEN
        RAISE EXCEPTION 'profiles must be a non-empty JSON object';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_each(p_profiles) AS profile(archetype, resume_data)
        WHERE pg_catalog.jsonb_typeof(profile.resume_data) <> 'object'
           OR profile.resume_data = '{}'::jsonb
           OR NOT EXISTS (
               SELECT 1
               FROM public.career_lane_definitions AS lane
               WHERE lane.archetype = profile.archetype
           )
    ) THEN
        RAISE EXCEPTION 'profiles contain an unknown archetype or empty resume object';
    END IF;

    SELECT id INTO target_base_resume_id
    FROM public.base_resume
    ORDER BY updated_at DESC
    LIMIT 1
    FOR UPDATE;

    IF target_base_resume_id IS NULL THEN
        RAISE EXCEPTION 'a global base resume must exist before lane profiles are saved';
    END IF;

    INSERT INTO public.archetype_resume_profiles (
        archetype,
        base_resume_id,
        profile_data,
        enabled
    )
    SELECT
        profile.archetype,
        target_base_resume_id,
        profile.resume_data,
        true
    FROM pg_catalog.jsonb_each(p_profiles) AS profile(archetype, resume_data)
    ON CONFLICT (archetype) DO UPDATE SET
        base_resume_id = EXCLUDED.base_resume_id,
        profile_data = EXCLUDED.profile_data,
        enabled = true,
        updated_at = pg_catalog.now();

    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.replace_archetype_resume_profiles(jsonb)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_archetype_resume_profiles(jsonb)
TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;
