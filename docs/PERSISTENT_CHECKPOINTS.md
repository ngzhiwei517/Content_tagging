# Persistent batch checkpoints

Local JSON checkpoints remain enabled with no configuration. To retain batches
when Streamlit replaces or redeploys the app container, configure either
Supabase REST or a direct Postgres connection.

1. Run the current `checkpoint_schema.sql` in Supabase SQL Editor or Postgres.
   Existing deployments must run it again after this update because it also
   creates the shared tagging worker slots and lease functions.
2. Add one backend to Streamlit Secrets.

Direct Postgres, including a Supabase Postgres connection URL:

```toml
[checkpoint]
database_url = "postgresql://..."
```

Direct Postgres is an optional deployment mode and requires installing
`psycopg[binary]` in that deployment. It is intentionally not part of the
default Streamlit Cloud requirements because the Supabase REST mode does not
need a database driver.

Supabase REST:

```toml
[checkpoint]
supabase_url = "https://PROJECT.supabase.co"
supabase_key = "SERVER_SIDE_KEY"
```

The project URL and Supabase Data API URL ending in `/rest/v1/` are both
accepted. The app normalizes the Data API form before building table requests.

The same values may be supplied as `CHECKPOINT_DATABASE_URL`, or
`CHECKPOINT_SUPABASE_URL` plus `CHECKPOINT_SUPABASE_KEY` environment variables.
`CHECKPOINT_TABLE` optionally changes the table name.

The worker pool allows three concurrent AI-tagging batches by default. Override
that server-side only when a controlled load test supports a higher value:

```toml
[tagging_workers]
max_concurrent_jobs = 3
```

`TAGGING_MAX_CONCURRENT_JOBS` is the equivalent environment variable. Values
are restricted to 1-16. Increasing this setting does not add CPU, memory,
database capacity, or provider quota.

Keep these settings server-side. The app persists only allowlisted workflow
state and sanitized tagging objects. Gemini/Apify/database credentials,
downloaded media, binary media fields and local media paths are excluded.
Recovery IDs are private bearer identifiers and should not be shared publicly.

Progress is saved automatically. Click **Continue later** to verify the current
batch was written to the recovery database before closing the app. A green
confirmation means the private link is safe to use after an app restart; a
warning means only the temporary local fallback is available.

The private `run` value in the current browser
URL identifies the batch and lets the app restore it after a reconnect or
restart. Keep that URL private because anyone with it can reopen the batch.
Opening the plain app URL starts a new independent batch, so separate tabs can
run separate jobs without being redirected to the last unfinished batch.

Remote checkpointing starts only after the current workflow contains at least
one post. Opening an empty app session does not create a Supabase/Postgres row;
the local fallback remains available from the first render.

## Shared tagging worker pool and write pattern

When persistent checkpoints are configured, every AI-tagging batch must claim
one database-backed worker slot before calling Gemini or the Apify fallback.
Three independent batches may run concurrently by default. The slot is released
after each bounded app execution, and an expired lease is cleared automatically
if a worker stops unexpectedly.

When all slots are busy, the app does not create a visible waiting queue or
start another provider call. The batch remains saved under its existing recovery
ID, and the user may try again or continue later from the private recovery link.

The queue uses the existing recovery ID and tagging job ID. Resuming from the
private recovery link therefore re-enters the same job and skips post positions
that already have a saved result.

Completed results are stored as one small object per post. The app no longer
rewrites a growing partial-results JSON snapshot every five posts. A completed
50-row checkpoint chunk may still be compacted once after every row in that
chunk is durable. Database statement cancellations with SQLSTATE `57014` are
retried from a fresh request/connection with bounded exponential backoff.

If persistent settings are present but the worker-pool functions are missing or
unavailable, tagging fails closed before provider work starts and asks the app
owner to apply the latest schema. Local-only development uses a process-local
multi-slot lock; that fallback coordinates sessions in one app process but not
multiple app instances.

This is bounded concurrency inside the Streamlit deployment, not an external
background-worker service. A deployment restart can pause in-process work, but
the saved recovery ID and per-post results allow the batch to continue without
repeating completed posts.
