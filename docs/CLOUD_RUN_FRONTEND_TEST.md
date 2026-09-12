# Isolated Cloud Run frontend test

This branch deploys the existing Streamlit interface as a separate Cloud Run
service. It does not replace the Streamlit Community Cloud app, update `main`,
or modify the existing `taggy-job-backend` service.

This is a deployment-test branch and should not be merged into `main` as-is:
its default `Dockerfile` intentionally starts Streamlit, while the backend
branch's default `Dockerfile` intentionally starts Uvicorn. If the Cloud Run
frontend is adopted permanently, keep separate frontend and backend container
definitions before promotion.

## Isolation model

```text
Existing beta (unchanged)
Streamlit Community Cloud -> taggy-job-backend -> taggy-posts

Parallel test
taggy-web-test -> taggy-job-backend-test -> taggy-posts-test
```

The test services may reuse the existing Secret Manager secret versions. This
keeps the secret values server-side, but Gemini and Apify quotas, provider
costs, and the Supabase project remain shared. Use small batches for the first
concurrency test.

## Before deploying

- Use Google Cloud project `taggy-508408` and region `asia-southeast1`.
- Confirm the existing six `taggy-*` Secret Manager secrets are enabled.
- Confirm `cloud_job_schema.sql` has already been applied successfully.
- Run backend commands from the clean
  `agent/cloud-run-concurrency-performance` worktree.
- Run frontend commands from this clean `agent/cloud-run-streamlit-test`
  worktree.
- Do not change the existing Streamlit app secrets or service URLs.

## 1. Create the separate test queue

Run in Windows Command Prompt:

```bat
gcloud config set project taggy-508408
gcloud tasks queues create taggy-posts-test --location=asia-southeast1 --max-concurrent-dispatches=9 --max-dispatches-per-second=9 --max-attempts=5 --min-backoff=10s --max-backoff=300s --max-doublings=4
```

If the queue already exists, use:

```bat
gcloud tasks queues update taggy-posts-test --location=asia-southeast1 --max-concurrent-dispatches=9 --max-dispatches-per-second=9 --max-attempts=5 --min-backoff=10s --max-backoff=300s --max-doublings=4
```

## 2. Deploy the separate test backend

Change to the `agent/cloud-run-concurrency-performance` worktree, then run:

```bat
gcloud run deploy taggy-job-backend-test --source=. --region=asia-southeast1 --no-invoker-iam-check --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=1 --max-instances=9 --min-instances=0 --timeout=1800 --memory=2Gi --cpu=2 --set-env-vars="GOOGLE_CLOUD_PROJECT=taggy-508408,GOOGLE_CLOUD_LOCATION=asia-southeast1,TAGGY_CLOUD_TASKS_QUEUE=taggy-posts-test,TAGGY_MAX_POSTS_PER_JOB=100,TAGGY_MAX_POST_ATTEMPTS=5,TAGGY_TASK_DEADLINE_SECONDS=1800,TAGGY_POST_LEASE_SECONDS=2100" --set-secrets="GEMINI_API_KEY=taggy-gemini-api-key:latest,APIFY_TOKEN=taggy-apify-token:latest,CHECKPOINT_SUPABASE_URL=taggy-supabase-url:latest,CHECKPOINT_SUPABASE_KEY=taggy-supabase-key:latest,TAGGY_BACKEND_API_KEY=taggy-backend-api-key:latest,TAGGY_TASK_API_KEY=taggy-task-api-key:latest"
```

Display and copy the new test backend URL:

```bat
gcloud run services describe taggy-job-backend-test --region=asia-southeast1 --format="value(status.url)"
```

Replace `TEST_BACKEND_URL` below with that exact URL:

```bat
gcloud run services update taggy-job-backend-test --region=asia-southeast1 --update-env-vars="TAGGY_CLOUD_WORKER_URL=TEST_BACKEND_URL"
```

Open `TEST_BACKEND_URL/v1/health` and confirm that `ready` is `true` before
deploying the frontend.

## 3. Deploy the separate Streamlit frontend

Change to the `agent/cloud-run-streamlit-test` worktree. Replace
`TEST_BACKEND_URL` with the URL copied above, then run:

```bat
gcloud run deploy taggy-web-test --source=. --region=asia-southeast1 --no-invoker-iam-check --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=3 --max-instances=3 --min-instances=0 --timeout=3600 --memory=2Gi --cpu=2 --session-affinity --set-env-vars="TAGGY_BACKEND_URL=TEST_BACKEND_URL,TAGGY_BACKEND_POLL_SECONDS=3,CHECKPOINT_TABLE=batch_checkpoint_objects" --set-secrets="GEMINI_API_KEY=taggy-gemini-api-key:latest,APIFY_TOKEN=taggy-apify-token:latest,CHECKPOINT_SUPABASE_URL=taggy-supabase-url:latest,CHECKPOINT_SUPABASE_KEY=taggy-supabase-key:latest,TAGGY_BACKEND_API_KEY=taggy-backend-api-key:latest"
```

Display the separate test URL:

```bat
gcloud run services describe taggy-web-test --region=asia-southeast1 --format="value(status.url)"
```

The container health endpoint is `TEST_FRONTEND_URL/_stcore/health`.

## 4. Controlled concurrency test

Use different browsers or incognito profiles so each participant has an
independent Streamlit session and recovery link.

1. Run one small three-post batch through Review and Export.
2. Run four separate three-post batches concurrently.
3. Reopen one recovery link and confirm completed posts are not repeated.
4. Check Cloud Run, Cloud Tasks, Supabase, Gemini and Apify usage.
5. Only if those checks pass, run nine separate three-post batches.

For each stage, record submission time, time to first completed post, total
completion time, failures, retries and recovery success. The queue should allow
jobs from different batches to make progress concurrently; one batch still
processes its own posts sequentially.

## Rollback

No traffic is switched automatically. If the test is unsuccessful, stop using
the `taggy-web-test` URL. With minimum instances set to zero, both test services
scale down when idle. Do not delete the test services or queue until all test
recovery links are no longer needed.

The existing Streamlit Community Cloud app, `taggy-job-backend`, `taggy-posts`
queue and `main` branch remain unchanged throughout this test.
