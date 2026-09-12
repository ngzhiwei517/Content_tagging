# Optional Cloud Run job backend

This backend moves long-running AI tagging out of the Streamlit session. It is
intended for the multi-user beta; the existing Streamlit execution path remains
the fallback when `[cloud_backend]` is not configured.

## Processing model

```text
Streamlit -> FastAPI job service -> Cloud Tasks -> one-post worker
                    |                       |
                    +------ Supabase -------+
```

- Each batch has at most one active post task, so one large batch cannot occupy
  every worker.
- The Cloud Tasks queue may run tasks from different batches concurrently.
- Start with three concurrent tasks, test with 1, 3 and 5 simultaneous users,
  then raise the queue and Cloud Run limits to nine after provider and cost
  checks pass.
- Each completed post is stored separately. A resume uses the same job and
  recovery IDs and does not reprocess completed positions.
- Temporary provider failures retry with exponential backoff. After five
  attempts, the batch pauses for owner attention instead of looping forever.

This is still an internal beta. The shared access key is server-managed and is
not individual user authentication or usage attribution.

## What the owner must configure

### 1. Add the Supabase schema

In the existing Supabase project, open **SQL Editor**, paste the complete
contents of `cloud_job_schema.sql`, and run it once. This adds new tables and
functions only; it does not replace or edit `batch_checkpoint_objects`.

Do not continue until the SQL editor reports success.

### 2. Prepare Google Cloud

Use project `taggy-508408` and region `asia-southeast1`. In Cloud Shell, run:

```bash
gcloud config set project taggy-508408
gcloud services enable run.googleapis.com cloudtasks.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud iam service-accounts create taggy-worker --display-name="Taggy Cloud Run worker"
gcloud projects add-iam-policy-binding taggy-508408 --member="serviceAccount:taggy-worker@taggy-508408.iam.gserviceaccount.com" --role="roles/cloudtasks.enqueuer"
```

In **Secret Manager**, create six secrets. Use these secret names, but enter
the real values only in Google Cloud:

| Secret name | Value |
| --- | --- |
| `taggy-gemini-api-key` | deployment Gemini key |
| `taggy-apify-token` | deployment Apify token |
| `taggy-supabase-url` | plain Supabase project URL |
| `taggy-supabase-key` | server-side Supabase secret/service key |
| `taggy-backend-api-key` | newly generated random access key |
| `taggy-task-api-key` | a different newly generated random task key |

Grant the `taggy-worker` service account **Secret Manager Secret Accessor** for
these six secrets. Never paste any value into source code, Git, logs, or this
document.

### 3. Create the queue

Create the first queue with conservative concurrency:

```bash
gcloud tasks queues create taggy-posts --location=asia-southeast1 --max-concurrent-dispatches=3 --max-dispatches-per-second=3 --max-attempts=5 --min-backoff=10s --max-backoff=300s --max-doublings=4
```

The application and queue both use five attempts. Do not make the queue retry
indefinitely.

### 4. Deploy the service

The first deployment creates the service URL. `TAGGY_CLOUD_WORKER_URL` is added
in the following update after that URL exists.

```bash
gcloud run deploy taggy-job-backend --source=. --region=asia-southeast1 --allow-unauthenticated --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=1 --max-instances=3 --min-instances=0 --timeout=1800 --memory=2Gi --cpu=2 --set-env-vars="GOOGLE_CLOUD_PROJECT=taggy-508408,GOOGLE_CLOUD_LOCATION=asia-southeast1,TAGGY_CLOUD_TASKS_QUEUE=taggy-posts,TAGGY_MAX_POSTS_PER_JOB=100,TAGGY_MAX_POST_ATTEMPTS=5,TAGGY_TASK_DEADLINE_SECONDS=1800,TAGGY_POST_LEASE_SECONDS=2100" --set-secrets="GEMINI_API_KEY=taggy-gemini-api-key:latest,APIFY_TOKEN=taggy-apify-token:latest,CHECKPOINT_SUPABASE_URL=taggy-supabase-url:latest,CHECKPOINT_SUPABASE_KEY=taggy-supabase-key:latest,TAGGY_BACKEND_API_KEY=taggy-backend-api-key:latest,TAGGY_TASK_API_KEY=taggy-task-api-key:latest"

BACKEND_URL="$(gcloud run services describe taggy-job-backend --region=asia-southeast1 --format='value(status.url)')"
gcloud run services update taggy-job-backend --region=asia-southeast1 --update-env-vars="TAGGY_CLOUD_WORKER_URL=${BACKEND_URL}"
```

The service URL is public because Streamlit Cloud must reach it, but every job
and worker endpoint is protected by a separate server-managed key. API docs are
disabled. Do not expose either key in the browser or to beta users.

### 5. Connect Streamlit

Add this to Streamlit Cloud Secrets using the Cloud Run URL and the same value
stored in `taggy-backend-api-key`:

```toml
[cloud_backend]
url = "https://replace-with-cloud-run-url"
api_key = "replace-with-backend-access-key"
poll_seconds = 3
```

Restart the Streamlit app. When this section is complete, AI tagging uses the
cloud service. Metrics-only mode and the rest of the five-step UI remain in
Streamlit.

## Verification before raising concurrency

1. Open the Cloud Run URL followed by `/healthz`; confirm `ready` is `true`.
2. Submit a one-post job in Taggy and complete Review and Export.
3. Start three separate recovery links at the same time. Confirm all progress
   independently and completed posts are present in `taggy_cloud_job_posts`.
4. Interrupt one browser and reopen its private recovery link. Confirm the
   existing job continues and completed posts are skipped.
5. Simulate a temporary provider failure. Confirm it retries, then pauses after
   the bounded attempt limit without deleting completed rows.
6. Check Cloud Run logs, Cloud Tasks queue metrics, Supabase query health,
   Gemini/Apify usage and the Google Cloud budget before each increase.

After the 1-, 3- and 5-user tests pass, raise both controls together:

```bash
gcloud tasks queues update taggy-posts --location=asia-southeast1 --max-concurrent-dispatches=9 --max-dispatches-per-second=9
gcloud run services update taggy-job-backend --region=asia-southeast1 --max-instances=9
```

Keep Cloud Run container concurrency at `1`; the queue controls total parallel
post processing. The Google Cloud budget sends alerts but is not a hard spend
cap.

## Storage maintenance

The new tables remove the previous full-batch rewrite pattern, but completed
job rows still use database space. Review retention with the project owner. For
example, after confirming that recovery links older than 30 days are no longer
needed, an administrator may remove only old terminal jobs; their post rows are
deleted by the foreign-key cascade:

```sql
delete from public.taggy_cloud_jobs
where updated_at < clock_timestamp() - interval '30 days'
  and status in ('completed', 'needs_attention');
```

Preview the matching job IDs and counts before running any deletion. Never run
this automatically until the owner has approved a retention period.

## Rollback

Remove the entire `[cloud_backend]` section from Streamlit Secrets and restart
the Streamlit app. Taggy then uses its existing local/checkpointed execution
path. Do not delete cloud job rows until any affected recovery links are no
longer needed.
