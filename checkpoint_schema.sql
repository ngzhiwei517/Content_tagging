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
