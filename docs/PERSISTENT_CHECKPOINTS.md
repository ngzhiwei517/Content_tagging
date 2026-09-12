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

1. Run `checkpoint_schema.sql` once in Supabase SQL Editor or Postgres.
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
recovery database before closing the app. A green confirmation means the
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
