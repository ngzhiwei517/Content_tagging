# Apify beta safeguards

The hosted beta uses direct public retrieval first and a shared Apify token only
when paid fallback is required. The safeguards below reduce accidental shared
spending; they do not turn the Streamlit pilot into a production job queue.

## Required Apify account settings

1. Open Apify **Settings -> Notifications** and enable billing and usage email
   notifications.
2. Open **Billing -> Limits** and set the account hard usage limit. For the
   current beta allowance, use **$5**.
3. Keep the dedicated token in Streamlit Secrets as `APIFY_TOKEN`. Never put it
   in source code, screenshots, exports, or client-side controls.

Apify does not document an arbitrary custom email threshold such as exactly
$4. The app therefore shows its own warning and blocks new paid fallback before
the account hard limit; Apify's notifications remain the out-of-app alert.

## Streamlit Secrets

The safe beta defaults are a warning at $3.50 and a stop at $4.00. No additional
app setting is required when those values are correct.

To make the values explicit or change them, add:

```toml
APIFY_TOKEN = "replace-with-the-deployment-token"

[apify_guard]
enabled = true
warning_usd = 3.50
stop_usd = 4.00
fail_closed = true
```

Equivalent environment variables are `APIFY_GUARD_ENABLED`,
`APIFY_GUARD_WARNING_USD`, `APIFY_GUARD_STOP_USD`, and
`APIFY_GUARD_FAIL_CLOSED`.

Keep `fail_closed = true` for shared testing. If the usage endpoint cannot be
verified, the app pauses new paid fallback instead of risking an unknown charge.
Direct retrieval remains available.

## Runtime behavior

- The app reads `GET /v2/users/me/limits` with the token in an authorization
  header. The response supplies current monthly usage, the account limit,
  usage-cycle dates, and active Actor job count.
- Usage is cached briefly for the UI but refreshed immediately before every
  paid Actor start.
- If Apify reports an active Actor job on the shared account, the next paid
  start pauses for a later retry.
- At the warning threshold, users see a shared-capacity warning.
- At the stop threshold, new paid Actor starts are blocked before they run.
- Only one paid Actor call can run at a time inside one Streamlit server process.
- Existing row and batch checkpoints continue to save completed progress.

The one-at-a-time lock coordinates users connected to the same running app
process. The account-level active-job check reduces overlap with another
instance but cannot eliminate an exact simultaneous race. If the deployment is
later scaled to multiple replicas or services, a shared database lease or real
queue is required. Supabase/Postgres checkpoint storage should also be
configured and live-tested before relying on recovery after a redeploy; local
checkpoints alone are temporary.

## Beta smoke test

1. Temporarily set `warning_usd` and `stop_usd` below the current usage in a
   non-production test deployment.
2. Confirm the warning or blocked message appears without showing the token.
3. Attempt a post that requires fallback and confirm no Actor starts.
4. Raise the stop threshold above current usage.
5. Open two browser sessions and start two fallback-requiring batches together.
6. Confirm only one Actor call runs and the other batch pauses safely.
7. Confirm direct-only posts and saved checkpoints remain usable.
8. Restore the intended $3.50 / $4.00 values.
