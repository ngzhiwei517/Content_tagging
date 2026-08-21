# Persistent batch checkpoints

Local JSON checkpoints remain enabled with no configuration. To retain batches
when Streamlit replaces or redeploys the app container, configure either
Supabase REST or a direct Postgres connection.

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
For queued MelodyIQ reports, checkpoints keep only the report ID, track and
artist labels, selected sound IDs and import choice. Live report responses and
temporary signed CSV export URLs are fetched again after recovery and are never
stored in the checkpoint.

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
