create table if not exists public.batch_checkpoint_objects (
    recovery_id text not null check (recovery_id ~ '^[a-f0-9]{32}$'),
    object_key text not null,
    payload jsonb not null,
    updated_at timestamptz not null default now(),
    primary key (recovery_id, object_key)
);

create index if not exists batch_checkpoint_objects_updated_at_idx
    on public.batch_checkpoint_objects (updated_at desc);

alter table public.batch_checkpoint_objects enable row level security;

-- Bounded concurrent admission control. Each Streamlit session claims one
-- worker slot before Gemini or Apify work and releases it after one bounded
-- execution. Extra sessions are not queued; they retain their recovery link
-- and may retry when capacity becomes available.
create table if not exists public.tagging_worker_slots (
    slot_id integer primary key check (slot_id between 1 and 16),
    recovery_id text check (
        recovery_id is null or recovery_id ~ '^[a-f0-9]{32}$'
    ),
    job_id text check (job_id is null or job_id ~ '^[a-f0-9]{32}$'),
    owner_id text check (owner_id is null or owner_id ~ '^[a-f0-9]{32}$'),
    lease_until timestamptz,
    updated_at timestamptz not null default clock_timestamp(),
    check (
        (recovery_id is null and job_id is null and owner_id is null and lease_until is null)
        or
        (recovery_id is not null and job_id is not null and owner_id is not null and lease_until is not null)
    )
);

create unique index if not exists tagging_worker_slots_job_idx
    on public.tagging_worker_slots (recovery_id, job_id)
    where recovery_id is not null;

alter table public.tagging_worker_slots enable row level security;

create or replace function public.tagging_pool_claim(
    p_recovery_id text,
    p_job_id text,
    p_owner_id text,
    p_lease_seconds integer default 7200,
    p_max_workers integer default 3
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_capacity integer := greatest(1, least(16, coalesce(p_max_workers, 3)));
    v_lease_until timestamptz;
    v_slot_id integer;
    v_existing_owner_id text;
    v_active_workers integer := 0;
begin
    if p_recovery_id !~ '^[a-f0-9]{32}$'
       or p_job_id !~ '^[a-f0-9]{32}$'
       or p_owner_id !~ '^[a-f0-9]{32}$' then
        raise exception 'Invalid tagging worker identifier';
    end if;

    -- Serialize only the very short slot-allocation transaction. Tagging itself
    -- remains concurrent and never holds a database lock.
    perform pg_advisory_xact_lock(hashtext('tagging_worker_pool_v1'));

    insert into public.tagging_worker_slots (slot_id)
    select generate_series(1, v_capacity)
    on conflict (slot_id) do nothing;

    update public.tagging_worker_slots
    set recovery_id = null,
        job_id = null,
        owner_id = null,
        lease_until = null,
        updated_at = v_now
    where lease_until is not null
      and lease_until <= v_now;

    v_lease_until := v_now + make_interval(
        secs => greatest(60, least(7200, coalesce(p_lease_seconds, 7200)))
    );

    select slot_id, owner_id into v_slot_id, v_existing_owner_id
    from public.tagging_worker_slots
    where recovery_id = p_recovery_id
      and job_id = p_job_id
      and lease_until > v_now
    order by slot_id
    limit 1;

    if v_slot_id is not null then
        if v_existing_owner_id is distinct from p_owner_id then
            select count(*) into v_active_workers
            from public.tagging_worker_slots
            where lease_until > v_now;

            return jsonb_build_object(
                'acquired', false,
                'reason', 'job_active',
                'queue_position', 0,
                'active_recovery_id', p_recovery_id,
                'lease_until', null,
                'slot_id', v_slot_id,
                'active_workers', v_active_workers,
                'capacity', v_capacity
            );
        end if;

        update public.tagging_worker_slots
        set lease_until = v_lease_until,
            updated_at = v_now
        where slot_id = v_slot_id;

        select count(*) into v_active_workers
        from public.tagging_worker_slots
        where lease_until > v_now;

        return jsonb_build_object(
            'acquired', true,
            'reason', 'acquired',
            'queue_position', 0,
            'active_recovery_id', p_recovery_id,
            'lease_until', v_lease_until,
            'slot_id', v_slot_id,
            'active_workers', v_active_workers,
            'capacity', v_capacity
        );
    end if;

    select slot_id into v_slot_id
    from public.tagging_worker_slots
    where slot_id <= v_capacity
      and lease_until is null
    order by slot_id
    limit 1;

    if v_slot_id is not null then
        update public.tagging_worker_slots
        set recovery_id = p_recovery_id,
            job_id = p_job_id,
            owner_id = p_owner_id,
            lease_until = v_lease_until,
            updated_at = v_now
        where slot_id = v_slot_id;

        select count(*) into v_active_workers
        from public.tagging_worker_slots
        where lease_until > v_now;

        return jsonb_build_object(
            'acquired', true,
            'reason', 'acquired',
            'queue_position', 0,
            'active_recovery_id', p_recovery_id,
            'lease_until', v_lease_until,
            'slot_id', v_slot_id,
            'active_workers', v_active_workers,
            'capacity', v_capacity
        );
    end if;

    select count(*) into v_active_workers
    from public.tagging_worker_slots
    where lease_until > v_now;

    return jsonb_build_object(
        'acquired', false,
        'reason', 'capacity_full',
        'queue_position', 0,
        'active_recovery_id', '',
        'lease_until', null,
        'slot_id', null,
        'active_workers', v_active_workers,
        'capacity', v_capacity
    );
end;
$$;

create or replace function public.tagging_pool_release(
    p_recovery_id text,
    p_job_id text,
    p_owner_id text
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    v_released boolean := false;
begin
    update public.tagging_worker_slots
    set recovery_id = null,
        job_id = null,
        owner_id = null,
        lease_until = null,
        updated_at = clock_timestamp()
    where recovery_id = p_recovery_id
      and job_id = p_job_id
      and owner_id = p_owner_id;

    v_released := found;
    return v_released;
end;
$$;

revoke execute on function public.tagging_pool_claim(text, text, text, integer, integer)
    from public;
revoke execute on function public.tagging_pool_release(text, text, text)
    from public;

-- Supabase server-side secret/service-role requests may call the functions;
-- browser roles cannot inspect or operate the queue directly.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant execute on function public.tagging_pool_claim(text, text, text, integer, integer) to service_role';
        execute 'grant execute on function public.tagging_pool_release(text, text, text) to service_role';
    end if;
end;
$$;
