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

The same values may be supplied as `CHECKPOINT_DATABASE_URL`, or
`CHECKPOINT_SUPABASE_URL` plus `CHECKPOINT_SUPABASE_KEY` environment variables.
`CHECKPOINT_TABLE` optionally changes the table name.

Keep these settings server-side. The app persists only allowlisted workflow
state and sanitized tagging objects. Gemini/Apify/database credentials,
downloaded media, binary media fields and local media paths are excluded.
Recovery IDs are private bearer identifiers and should not be shared publicly.

Users normally select **Save this batch** and bookmark or copy the private link.
The recovery ID stays inside that link. The **Open a saved batch** area accepts
the raw ID only as a fallback when someone no longer has the full link.

Remote checkpointing starts only after the current workflow contains at least
one post. Opening an empty app session does not create a Supabase/Postgres row;
the local fallback remains available from the first render.
