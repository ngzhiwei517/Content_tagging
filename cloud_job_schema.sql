-- Additive schema for the optional FastAPI/Cloud Run job backend.
-- Existing Streamlit checkpoint tables and recovery links are unchanged.

create table if not exists public.taggy_cloud_jobs (
    job_id text primary key check (job_id ~ '^[a-f0-9]{32}$'),
    recovery_id text not null check (recovery_id ~ '^[a-f0-9]{32}$'),
    request_hash text not null check (request_hash ~ '^[a-f0-9]{64}$'),
    model text not null,
    status text not null default 'queued' check (
        status in ('queued', 'running', 'needs_attention', 'completed')
    ),
    total_posts integer not null check (total_posts between 1 and 500),
    dispatch_generation integer not null default 0 check (dispatch_generation >= 0),
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp()
);

create index if not exists taggy_cloud_jobs_recovery_idx
    on public.taggy_cloud_jobs (recovery_id, updated_at desc);

create table if not exists public.taggy_cloud_job_posts (
    job_id text not null references public.taggy_cloud_jobs(job_id) on delete cascade,
    position integer not null check (position >= 0),
    status text not null default 'pending' check (
        status in ('pending', 'running', 'retryable', 'failed', 'completed')
    ),
    input_payload jsonb not null,
    result_payload jsonb,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    worker_id text check (worker_id is null or worker_id ~ '^[a-f0-9]{32}$'),
    lease_until timestamptz,
    error_code text,
    updated_at timestamptz not null default clock_timestamp(),
    primary key (job_id, position),
    check (
        (status = 'completed' and result_payload is not null)
        or status <> 'completed'
    )
);

create index if not exists taggy_cloud_job_posts_status_idx
    on public.taggy_cloud_job_posts (job_id, status, position);

alter table public.taggy_cloud_jobs enable row level security;
alter table public.taggy_cloud_job_posts enable row level security;

create or replace function public.taggy_cloud_create_job(
    p_job_id text,
    p_recovery_id text,
    p_request_hash text,
    p_model text,
    p_posts jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_existing public.taggy_cloud_jobs%rowtype;
    v_count integer;
begin
    if p_job_id !~ '^[a-f0-9]{32}$'
       or p_recovery_id !~ '^[a-f0-9]{32}$'
       or p_request_hash !~ '^[a-f0-9]{64}$' then
        raise exception 'Invalid cloud job identifier';
    end if;
    if jsonb_typeof(p_posts) <> 'array' then
        raise exception 'Cloud job posts must be an array';
    end if;
    v_count := jsonb_array_length(p_posts);
    if v_count < 1 or v_count > 500 then
        raise exception 'Cloud job post count is outside the supported range';
    end if;

    select * into v_existing
    from public.taggy_cloud_jobs
    where job_id = p_job_id;

    if found then
        if v_existing.recovery_id <> p_recovery_id
           or v_existing.request_hash <> p_request_hash then
            raise exception 'TAGGY_JOB_CONFLICT';
        end if;
        return to_jsonb(v_existing);
    end if;

    insert into public.taggy_cloud_jobs (
        job_id, recovery_id, request_hash, model, total_posts
    ) values (
        p_job_id, p_recovery_id, p_request_hash, p_model, v_count
    );

    insert into public.taggy_cloud_job_posts (
        job_id, position, input_payload
    )
    select
        p_job_id,
        item.ordinality::integer - 1,
        item.value
    from jsonb_array_elements(p_posts) with ordinality as item(value, ordinality);

    select * into v_existing
    from public.taggy_cloud_jobs
    where job_id = p_job_id;
    return to_jsonb(v_existing);
end;
$$;

create or replace function public.taggy_cloud_claim_post(
    p_job_id text,
    p_position integer,
    p_worker_id text,
    p_lease_seconds integer default 2100
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_row public.taggy_cloud_job_posts%rowtype;
    v_model text;
begin
    if p_job_id !~ '^[a-f0-9]{32}$'
       or p_worker_id !~ '^[a-f0-9]{32}$'
       or p_position < 0 then
        raise exception 'Invalid cloud job claim';
    end if;

    select model into v_model
    from public.taggy_cloud_jobs
    where job_id = p_job_id;
    if not found then
        return jsonb_build_object('state', 'missing');
    end if;

    update public.taggy_cloud_job_posts
    set status = 'running',
        worker_id = p_worker_id,
        lease_until = clock_timestamp() + make_interval(
            secs => greatest(120, least(3600, coalesce(p_lease_seconds, 2100)))
        ),
        attempt_count = attempt_count + 1,
        error_code = null,
        updated_at = clock_timestamp()
    where job_id = p_job_id
      and position = p_position
      and (
          status in ('pending', 'retryable')
          or (status = 'running' and lease_until <= clock_timestamp())
      )
    returning * into v_row;

    if found then
        update public.taggy_cloud_jobs
        set status = 'running', updated_at = clock_timestamp()
        where job_id = p_job_id;
        return jsonb_build_object(
            'state', 'claimed',
            'input', v_row.input_payload,
            'model', v_model,
            'attempt_count', v_row.attempt_count
        );
    end if;

    select * into v_row
    from public.taggy_cloud_job_posts
    where job_id = p_job_id and position = p_position;
    if not found then
        return jsonb_build_object('state', 'missing');
    end if;
    if v_row.status = 'completed' then
        return jsonb_build_object(
            'state', 'completed',
            'result', v_row.result_payload
        );
    end if;
    if v_row.status = 'failed' then
        return jsonb_build_object('state', 'failed');
    end if;
    return jsonb_build_object('state', 'busy');
end;
$$;

create or replace function public.taggy_cloud_complete_post(
    p_job_id text,
    p_position integer,
    p_worker_id text,
    p_result jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_changed boolean := false;
    v_complete boolean := false;
begin
    if p_result is null or jsonb_typeof(p_result) <> 'object' then
        raise exception 'Cloud job result must be a JSON object';
    end if;

    update public.taggy_cloud_job_posts
    set status = 'completed',
        result_payload = p_result,
        worker_id = null,
        lease_until = null,
        error_code = null,
        updated_at = clock_timestamp()
    where job_id = p_job_id
      and position = p_position
      and status = 'running'
      and worker_id = p_worker_id;
    v_changed := found;

    if not v_changed then
        select exists (
            select 1
            from public.taggy_cloud_job_posts
            where job_id = p_job_id
              and position = p_position
              and status = 'completed'
        ) into v_changed;
    end if;

    select not exists (
        select 1
        from public.taggy_cloud_job_posts
        where job_id = p_job_id and status <> 'completed'
    ) into v_complete;

    update public.taggy_cloud_jobs
    set status = case when v_complete then 'completed' else 'running' end,
        updated_at = clock_timestamp()
    where job_id = p_job_id;

    return jsonb_build_object('completed', v_changed, 'job_complete', v_complete);
end;
$$;

create or replace function public.taggy_cloud_fail_post(
    p_job_id text,
    p_position integer,
    p_worker_id text,
    p_error_code text,
    p_retryable boolean default true
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_changed boolean := false;
begin
    update public.taggy_cloud_job_posts
    set status = case when p_retryable then 'retryable' else 'failed' end,
        worker_id = null,
        lease_until = null,
        error_code = left(coalesce(p_error_code, 'PROCESSING_FAILED'), 80),
        updated_at = clock_timestamp()
    where job_id = p_job_id
      and position = p_position
      and status = 'running'
      and worker_id = p_worker_id;
    v_changed := found;

    update public.taggy_cloud_jobs
    set status = case when p_retryable then 'queued' else 'needs_attention' end,
        updated_at = clock_timestamp()
    where job_id = p_job_id and v_changed;

    return jsonb_build_object('saved', v_changed);
end;
$$;

create or replace function public.taggy_cloud_resume_job(p_job_id text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_job public.taggy_cloud_jobs%rowtype;
begin
    update public.taggy_cloud_job_posts
    set status = 'pending',
        worker_id = null,
        lease_until = null,
        error_code = null,
        updated_at = clock_timestamp()
    where job_id = p_job_id
      and (
          status in ('retryable', 'failed')
          or (status = 'running' and lease_until <= clock_timestamp())
      );

    update public.taggy_cloud_jobs
    set status = case
            when not exists (
                select 1 from public.taggy_cloud_job_posts
                where job_id = p_job_id and status <> 'completed'
            ) then 'completed'
            else 'queued'
        end,
        dispatch_generation = dispatch_generation + 1,
        updated_at = clock_timestamp()
    where job_id = p_job_id
    returning * into v_job;

    if not found then
        raise exception 'Cloud job was not found';
    end if;
    return to_jsonb(v_job);
end;
$$;

revoke all on table public.taggy_cloud_jobs from anon, authenticated;
revoke all on table public.taggy_cloud_job_posts from anon, authenticated;
revoke execute on function public.taggy_cloud_create_job(text, text, text, text, jsonb)
    from public;
revoke execute on function public.taggy_cloud_claim_post(text, integer, text, integer)
    from public;
revoke execute on function public.taggy_cloud_complete_post(text, integer, text, jsonb)
    from public;
revoke execute on function public.taggy_cloud_fail_post(text, integer, text, text, boolean)
    from public;
revoke execute on function public.taggy_cloud_resume_job(text)
    from public;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant select, insert, update, delete on public.taggy_cloud_jobs to service_role';
        execute 'grant select, insert, update, delete on public.taggy_cloud_job_posts to service_role';
        execute 'grant execute on function public.taggy_cloud_create_job(text, text, text, text, jsonb) to service_role';
        execute 'grant execute on function public.taggy_cloud_claim_post(text, integer, text, integer) to service_role';
        execute 'grant execute on function public.taggy_cloud_complete_post(text, integer, text, jsonb) to service_role';
        execute 'grant execute on function public.taggy_cloud_fail_post(text, integer, text, text, boolean) to service_role';
        execute 'grant execute on function public.taggy_cloud_resume_job(text) to service_role';
    end if;
end;
$$;
