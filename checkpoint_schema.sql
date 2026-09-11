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

-- Global FIFO admission control. The app claims this singleton lease before
-- any Gemini or Apify tagging work, then releases it after one bounded unit.
create table if not exists public.tagging_job_queue (
    recovery_id text primary key check (recovery_id ~ '^[a-f0-9]{32}$'),
    job_id text not null check (job_id ~ '^[a-f0-9]{32}$'),
    enqueued_at timestamptz not null default clock_timestamp(),
    touched_at timestamptz not null default clock_timestamp()
);

create index if not exists tagging_job_queue_order_idx
    on public.tagging_job_queue (enqueued_at, recovery_id);

create table if not exists public.tagging_worker_lease (
    singleton boolean primary key default true check (singleton),
    recovery_id text,
    job_id text,
    owner_id text,
    lease_until timestamptz,
    updated_at timestamptz not null default clock_timestamp()
);

insert into public.tagging_worker_lease (singleton)
values (true)
on conflict (singleton) do nothing;

alter table public.tagging_job_queue enable row level security;
alter table public.tagging_worker_lease enable row level security;

create or replace function public.tagging_queue_claim(
    p_recovery_id text,
    p_job_id text,
    p_owner_id text,
    p_lease_seconds integer default 7200
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_first_recovery_id text;
    v_position integer := 1;
    v_lease public.tagging_worker_lease%rowtype;
    v_expired_recovery_id text;
    v_expired_job_id text;
begin
    if p_recovery_id !~ '^[a-f0-9]{32}$'
       or p_job_id !~ '^[a-f0-9]{32}$'
       or p_owner_id !~ '^[a-f0-9]{32}$' then
        raise exception 'Invalid tagging queue identifier';
    end if;

    insert into public.tagging_job_queue (
        recovery_id,
        job_id,
        enqueued_at,
        touched_at
    )
    values (p_recovery_id, p_job_id, v_now, v_now)
    on conflict (recovery_id) do update
    set job_id = excluded.job_id,
        enqueued_at = case
            when public.tagging_job_queue.job_id <> excluded.job_id
                then excluded.enqueued_at
            else public.tagging_job_queue.enqueued_at
        end,
        touched_at = excluded.touched_at;

    insert into public.tagging_worker_lease (singleton)
    values (true)
    on conflict (singleton) do nothing;

    select * into v_lease
    from public.tagging_worker_lease
    where singleton = true
    for update;

    if v_lease.lease_until is not null and v_lease.lease_until <= v_now then
        v_expired_recovery_id := v_lease.recovery_id;
        v_expired_job_id := v_lease.job_id;
        update public.tagging_worker_lease
        set recovery_id = null,
            job_id = null,
            owner_id = null,
            lease_until = null,
            updated_at = v_now
        where singleton = true;
        v_lease.recovery_id := null;
        v_lease.job_id := null;
        v_lease.owner_id := null;
        v_lease.lease_until := null;
        if v_expired_recovery_id is distinct from p_recovery_id then
            delete from public.tagging_job_queue
            where recovery_id = v_expired_recovery_id
              and job_id = v_expired_job_id;
        end if;
    end if;

    -- Remove abandoned waiters. The currently polling job and a fresh active
    -- lease are always retained.
    delete from public.tagging_job_queue q
    where q.recovery_id <> p_recovery_id
      and q.touched_at < v_now - interval '5 minutes'
      and not (
          v_lease.lease_until is not null
          and v_lease.lease_until > v_now
          and q.recovery_id = v_lease.recovery_id
          and q.job_id = v_lease.job_id
      );

    if v_lease.lease_until is not null and v_lease.lease_until > v_now then
        if v_lease.recovery_id = p_recovery_id
           and v_lease.job_id = p_job_id
           and v_lease.owner_id = p_owner_id then
            update public.tagging_worker_lease
            set lease_until = v_now + make_interval(
                    secs => greatest(60, least(7200, coalesce(p_lease_seconds, 7200)))
                ),
                updated_at = v_now
            where singleton = true;
            return jsonb_build_object(
                'acquired', true,
                'queue_position', 1,
                'active_recovery_id', p_recovery_id,
                'lease_until', v_now + make_interval(
                    secs => greatest(60, least(7200, coalesce(p_lease_seconds, 7200)))
                )
            );
        end if;

        select 1 + count(*) into v_position
        from public.tagging_job_queue q
        where (q.enqueued_at, q.recovery_id) < (
            select mine.enqueued_at, mine.recovery_id
            from public.tagging_job_queue mine
            where mine.recovery_id = p_recovery_id
        );
        return jsonb_build_object(
            'acquired', false,
            'queue_position', greatest(2, v_position),
            'active_recovery_id', coalesce(v_lease.recovery_id, ''),
            'lease_until', v_lease.lease_until
        );
    end if;

    select q.recovery_id into v_first_recovery_id
    from public.tagging_job_queue q
    order by q.enqueued_at, q.recovery_id
    limit 1;

    if v_first_recovery_id = p_recovery_id then
        update public.tagging_worker_lease
        set recovery_id = p_recovery_id,
            job_id = p_job_id,
            owner_id = p_owner_id,
            lease_until = v_now + make_interval(
                secs => greatest(60, least(7200, coalesce(p_lease_seconds, 7200)))
            ),
            updated_at = v_now
        where singleton = true;
        return jsonb_build_object(
            'acquired', true,
            'queue_position', 1,
            'active_recovery_id', p_recovery_id,
            'lease_until', v_now + make_interval(
                secs => greatest(60, least(7200, coalesce(p_lease_seconds, 7200)))
            )
        );
    end if;

    select 1 + count(*) into v_position
    from public.tagging_job_queue q
    where (q.enqueued_at, q.recovery_id) < (
        select mine.enqueued_at, mine.recovery_id
        from public.tagging_job_queue mine
        where mine.recovery_id = p_recovery_id
    );
    return jsonb_build_object(
        'acquired', false,
        'queue_position', greatest(1, v_position),
        'active_recovery_id', '',
        'lease_until', null
    );
end;
$$;

create or replace function public.tagging_queue_release(
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
    update public.tagging_worker_lease
    set recovery_id = null,
        job_id = null,
        owner_id = null,
        lease_until = null,
        updated_at = clock_timestamp()
    where singleton = true
      and recovery_id = p_recovery_id
      and job_id = p_job_id
      and owner_id = p_owner_id;

    v_released := found;
    if v_released then
        delete from public.tagging_job_queue
        where recovery_id = p_recovery_id
          and job_id = p_job_id;
    end if;
    return v_released;
end;
$$;

revoke execute on function public.tagging_queue_claim(text, text, text, integer)
    from public;
revoke execute on function public.tagging_queue_release(text, text, text)
    from public;

-- Supabase server-side secret/service-role requests may call the functions;
-- browser roles cannot inspect or operate the queue directly.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant execute on function public.tagging_queue_claim(text, text, text, integer) to service_role';
        execute 'grant execute on function public.tagging_queue_release(text, text, text) to service_role';
    end if;
end;
$$;
