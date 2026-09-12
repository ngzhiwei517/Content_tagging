# Cloud Run frontend concurrency test

Streamlit Community Cloud gives one app a shared compute allowance. Running
several tagging sessions in that one process can trigger CPU throttling. This
test deploys the current, working Taggy branch to Cloud Run without changing or
removing the existing Community Cloud app.

The container deliberately limits native numerical and video libraries to one
CPU thread per session. Cloud Run then scales separate sessions across up to ten
instances instead of making nine users compete for one Streamlit process.

## Deploy the isolated test

Run these commands from this branch's worktree in Windows Command Prompt:

```bat
gcloud config set project taggy-508408
gcloud run deploy taggy-web-latest-test --source=. --region=asia-southeast1 --no-allow-unauthenticated --iap --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=1 --max-instances=10 --min-instances=0 --timeout=3600 --memory=2Gi --cpu=2 --session-affinity --set-env-vars="CHECKPOINT_TABLE=batch_checkpoint_objects" --set-secrets="GEMINI_API_KEY=taggy-gemini-api-key:latest,APIFY_TOKEN=taggy-apify-token:latest,CHECKPOINT_SUPABASE_URL=taggy-supabase-url:latest,CHECKPOINT_SUPABASE_KEY=taggy-supabase-key:latest"
gcloud run services describe taggy-web-latest-test --region=asia-southeast1 --format="value(status.url)"
```

This deployment processes tagging inside each autoscaled frontend instance. It
does not use the older three-worker queue and does not change the existing
`taggy-web-test`, `taggy-job-backend-test`, or Streamlit Community Cloud app.
The service remains private and uses Google Identity-Aware Proxy (IAP); do not
replace these flags with public or unauthenticated access while provider
secrets are attached.

## First IAP setup

For a personal Google Cloud project, the first IAP setup may require one visit
to the Google Cloud console:

1. Open Cloud Run and select `taggy-web-latest-test`.
2. Open **Security**, choose **Require authentication**, and select
   **Identity-Aware Proxy (IAP)**.
3. If prompted, configure the consent screen as **External** and choose
   **Auto generate credentials**.
4. Under the IAP policy, add only the Google accounts allowed to use Taggy.

Each approved user signs in with their own Google account. Gemini, Apify, and
Supabase credentials stay in Secret Manager and are never shared with users.

## Test safely

Use separate browsers or devices so each test represents a separate user.

1. Complete one small three-post batch through Review and Export.
2. Run two separate three-post batches at the same time.
3. Run four separate three-post batches at the same time.
4. If Cloud Run, Supabase, Gemini, and Apify show no errors, run nine batches.
5. Reopen one private recovery link and confirm completed work is restored.

Record time to first result, total time, and any retries at each stage. A
successful nine-user test means the sessions make progress independently; it
does not mean all nine jobs will finish at exactly the same time.

## Cost and rollback

Cloud Run can start up to ten 2-vCPU instances, so simultaneous tagging can
incur compute plus Gemini and Apify charges. `min-instances=0` lets the test
scale to zero when idle.

Rollback is immediate: stop sharing the `taggy-web-latest-test` URL and keep
using the existing Streamlit URL. No production traffic is switched by these
commands.
