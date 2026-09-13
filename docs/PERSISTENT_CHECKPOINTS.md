# Persistent batch checkpoints

Local JSON checkpoints remain enabled with no configuration. To retain batches
when Streamlit or Cloud Run replaces or redeploys the app container, configure
Google Cloud Storage, Supabase REST, or a direct Postgres connection.

## Google Cloud Storage (recommended for Cloud Run)

Cloud Run can use its service account automatically, so no storage credential
needs to be added to Streamlit Secrets. Configure the bucket name:

```toml
[checkpoint]
gcs_bucket = "taggy-508408-checkpoints"
gcs_project = "taggy-508408"
gcs_prefix = "taggy-checkpoints"
```

The equivalent environment variables are `CHECKPOINT_GCS_BUCKET`, optional
`CHECKPOINT_GCS_PROJECT`, and optional `CHECKPOINT_GCS_PREFIX`. When a GCS
bucket is configured, it takes precedence over the database settings. Existing
Supabase settings may remain attached as a rollback option.

Give the Cloud Run service account `roles/storage.objectUser` on this bucket
only. Keep uniform bucket-level access and public access prevention enabled.
The included `docs/gcs-checkpoint-lifecycle.json` deletes checkpoint objects
after 30 days.

## Database alternatives

1. Run the current `checkpoint_schema.sql` in Supabase SQL Editor or Postgres.
   This creates the checkpoint table and its access policies.
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

The app does not impose a fixed global limit on the number of separate
AI-tagging batches. It retains a per-batch execution safeguard so the same
recovery link cannot start the same checkpoint job twice at once. Actual
capacity depends on Cloud Run CPU and memory plus Gemini and Apify quotas.

Keep these settings server-side. The app persists only allowlisted workflow
state and sanitized tagging objects. Gemini/Apify/database credentials,
downloaded media, binary media fields and local media paths are excluded.
Recovery IDs are private bearer identifiers and should not be shared publicly.

Progress is saved locally immediately. Normal remote autosaves run
in bounded background workers so a slow recovery database cannot block uploads,
filters or another user's Streamlit session. Rapid reruns for the same recovery
ID are coalesced to the newest pending state. During tagging, completed rows are
written locally per post and uploaded as one compact partial snapshot per
bounded execution instead of one remote request per post.

Click **Continue later** to wait for and verify the current batch in the
configured recovery storage before closing the app. A green confirmation means the
private link is safe to use after an app restart; a warning means only the
temporary local fallback is available.

The normal app URL stays plain so opening or copying it into another tab starts
an independent batch. Only a private **Continue later** recovery link contains
`run=...`; opening the same recovery link in several tabs intentionally refers
to the same batch and therefore uses the same paid-work execution safeguard.

The private `run` value in the current browser
URL identifies the batch and lets the app restore it after a reconnect or
restart. Keep that URL private because anyone with it can reopen the batch.
Opening the plain app URL starts a new independent batch, so separate tabs can
run separate jobs without being redirected to the last unfinished batch.

Remote checkpointing starts only after the current workflow contains at least
one post. Opening an empty app session does not create a remote object or row;
the local fallback remains available from the first render.

## Concurrent tagging and write pattern

The app does not impose a fixed global limit on separate AI-tagging batches.
It does use the existing recovery ID and tagging job ID to prevent the same
checkpoint job from running twice at once. Resuming from the private recovery
link therefore re-enters the same job and skips post positions that already
have a saved result.

A GCS-only Cloud Run pilot must keep `max-instances=1` because this per-batch
execution safeguard is local to one app instance. Do not raise the Cloud Run
instance limit until a distributed execution lock or separate job service is
configured. Separate batches may run concurrently, with practical capacity
determined by Cloud Run resources and Gemini and Apify quotas.

Completed results are written to local checkpoint files immediately. At the
end of each bounded execution, the app uploads one compact partial snapshot to
the remote store instead of making that browser wait for one remote request per
post. A completed checkpoint chunk is compacted after every row in that chunk
is durable. Database statement cancellations with SQLSTATE `57014` are retried
from a fresh request/connection with bounded exponential backoff.

If an active Supabase/Postgres configuration is present but the worker-pool
functions are missing or unavailable, tagging fails closed before provider work
starts and asks the app owner to apply the latest schema. GCS-only and local
development use a process-local multi-slot lock; that fallback coordinates
sessions in one app process but not multiple app instances.

This is bounded concurrency inside the Streamlit deployment, not an external
background-worker service. A deployment restart can pause in-process work, but
the saved recovery ID and per-post results allow the batch to continue without
repeating completed posts.
