# Apify beta safeguards

The hosted beta uses direct public retrieval first and a shared Apify token only
when paid fallback is required. The safeguards below reduce accidental shared
spending; they do not turn the Streamlit pilot into a production job queue.

## Required Apify account settings

1. Open Apify **Settings -> Notifications** and enable billing and usage email
   notifications.
2. Open **Billing -> Limits** and set the account hard usage limit. For the
   current beta allowance through 9 September, use **$10**.
3. Keep the dedicated token in Streamlit Secrets as `APIFY_TOKEN`. Never put it
   in source code, screenshots, exports, or client-side controls.

Apify does not document an arbitrary custom email threshold such as exactly
$8. The app therefore sends private owner emails through the deployment's SMTP
account, restricts a second paid batch before the account hard limit, and keeps
an emergency stop. Apify's own notifications remain a separate backup alert.

## Streamlit Secrets

The current beta defaults are an owner warning at $8.00, a new-batch restriction
at $8.70, and an emergency stop at $9.50. Owner email alerts remain off until
the SMTP section below is configured and enabled.

To make the values explicit or change them, add:

```toml
APIFY_TOKEN = "replace-with-the-deployment-token"

[apify_guard]
enabled = true
warning_usd = 8.00
stop_usd = 8.70
emergency_stop_usd = 9.50
fail_closed = true

[apify_guard_email]
enabled = true
owner_email = "owner@example.com"
sender_email = "tagger@example.com"
smtp_host = "smtp.example.com"
smtp_port = 587
smtp_username = "tagger@example.com"
smtp_password = "replace-with-the-smtp-password"
use_tls = true
use_ssl = false
```

Equivalent environment variables are `APIFY_GUARD_ENABLED`,
`APIFY_GUARD_WARNING_USD`, `APIFY_GUARD_STOP_USD`,
`APIFY_GUARD_EMERGENCY_STOP_USD`, and `APIFY_GUARD_FAIL_CLOSED`.

Email equivalents are `APIFY_ALERT_EMAIL_ENABLED`,
`APIFY_ALERT_OWNER_EMAIL`, `APIFY_ALERT_SENDER_EMAIL`,
`APIFY_ALERT_SMTP_HOST`, `APIFY_ALERT_SMTP_PORT`,
`APIFY_ALERT_SMTP_USERNAME`, `APIFY_ALERT_SMTP_PASSWORD`,
`APIFY_ALERT_SMTP_USE_TLS`, and `APIFY_ALERT_SMTP_USE_SSL`.

Use the SMTP host, port and credentials supplied by the organisation's email
administrator. The password stays in Streamlit Secrets and is never included
in the alert, app UI, checkpoint, or source code.

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
- At the warning threshold, the owner receives a private email. Ordinary users
  do not see the usage amount or threshold.
- At $8.70, the owner receives a second email and the app freezes admission to
  the batch that most recently owned the paid lane below that threshold.
- The admitted batch may continue; another batch is paused before its paid call
  and sees only neutral capacity and recovery wording.
- At $9.50, all paid starts pause, including the admitted batch's next Actor
  call. The owner receives an emergency email.
- If an AI-tagging or Metrics-only run pauses, the user can select **Save link
  & continue later**, keep the private recovery link, and reopen it after access
  is restored. Reopening the link requires a manual resume action and reuses
  completed checkpointed posts.
- Only one paid Actor call can run at a time inside one Streamlit server process.
- Existing row and batch checkpoints continue to save completed progress.

Warning, restriction, and emergency emails are deduplicated separately for each
usage cycle on the app's local filesystem. A redeploy that clears local state
can cause one alert to be sent again. SMTP failure never disables the spending
guard: the app logs a non-sensitive failure category and retries later while
paid work remains subject to the same stop rules.

The admitted owner and one-at-a-time lock coordinate users connected to the same
running app process. The owner lease is deliberately fail-closed after a server
restart at or above $8.70 rather than guessing which user was active. The
account-level active-job check reduces overlap with another instance but cannot
eliminate an exact simultaneous race. Multiple replicas require a shared
database lease or real queue. Supabase/Postgres checkpoint storage should also
be configured and live-tested before relying on recovery after a redeploy;
local checkpoints alone are temporary.

## Beta smoke test

1. Temporarily set all three thresholds below the current usage in a
   non-production test deployment.
2. Confirm the owner receives the warning email and the app shows no dollar
   amount to ordinary users.
3. Confirm a blocked user sees only the neutral fallback-unavailable message.
4. Start one paid batch below the restriction threshold, then move the test
   threshold below current usage.
5. Confirm that same batch can make its next paid call while a different batch
   pauses and receives the recovery-link prompt.
6. Move the emergency threshold below current usage and confirm the admitted
   batch's next paid call also pauses.
7. Confirm direct-only posts and saved checkpoints remain usable.
8. Restore the intended $8.00 / $8.70 / $9.50 values.
