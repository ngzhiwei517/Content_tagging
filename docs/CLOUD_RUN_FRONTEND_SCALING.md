# Cloud Run pilot configuration

For a plain-language overview of the complete setup, GitHub behavior, storage,
link naming, reliability, and routine checks, see
[`TAGGY_CLOUD_OPERATIONS_GUIDE.md`](TAGGY_CLOUD_OPERATIONS_GUIDE.md).

Taggy is still a Streamlit application. Cloud Run replaces Streamlit Community
Cloud as the host, and private Google Cloud Storage (GCS) replaces Supabase as
the primary recovery store. Supabase is not active in the current Cloud Run
configuration.

## Current validated service shape

The `taggy-web-latest-test` service in `asia-southeast1` currently uses:

- one maximum instance and zero minimum instances;
- 2 vCPU and 2 GiB memory;
- container concurrency 80;
- a 3,600-second request timeout; and
- session affinity.

The one-instance maximum is intentional. Streamlit keeps upload sessions and
generated media downloads in the frontend process. Live multi-instance testing
showed an upload could be created on one instance and sent to another, causing
`400 Invalid session_id`. Session affinity alone did not prevent this. Keep the
service at one instance until those assets move to shared storage or a separate
job architecture.

Concurrency 80 is a simultaneous HTTP/WebSocket request allowance for the one
container. It is not 80 users, 80 posts, or 80 actions per second. One browser
can hold a WebSocket and make additional upload/download requests.

## Deploy the public service

Run only from an approved branch. Both provider secrets are mounted as files so
their `latest` versions can rotate without rebuilding the app.

```bat
gcloud config set project taggy-508408
gcloud run deploy taggy-web-latest-test --source=. --region=asia-southeast1 --no-invoker-iam-check --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=80 --max-instances=1 --min-instances=0 --timeout=3600 --memory=2Gi --cpu=2 --cpu-boost --session-affinity --set-env-vars="CHECKPOINT_GCS_BUCKET=taggy-508408-checkpoints,CHECKPOINT_GCS_PROJECT=taggy-508408,CHECKPOINT_GCS_PREFIX=taggy-checkpoints,APIFY_TOKEN_FILE=/var/secrets/apify/token,GEMINI_API_KEY_FILE=/var/secrets/gemini/key" --set-secrets="/var/secrets/apify/token=taggy-apify-token:latest,/var/secrets/gemini/key=taggy-gemini-api-key:latest"
gcloud run services describe taggy-web-latest-test --region=asia-southeast1 --format="value(status.url)"
```

For a zero-traffic rehearsal, add `--no-traffic --tag=hot-secrets-test` to the
deploy command. Do not move traffic away from a revision while users have active
tagging runs.

## Rotate a provider key without redeploying

1. Open **Security > Secret Manager > `taggy-apify-token`**.
2. Add the replacement as a new secret version. Do not paste it into source,
   logs, screenshots, or deployment commands.
3. Start one small new metrics/tagging run and confirm Apify succeeds.
4. Disable the prior secret version only after that check passes.

Cloud Run resolves the `latest` version whenever the mounted file is read. The
app reads this file at the beginning of each new metrics/tagging action. A job
already in progress keeps the credential it started with; the next action uses
the replacement.

Repeat the same process for `taggy-gemini-api-key` when rotating Gemini.

## Private recovery storage

The bucket is `gs://taggy-508408-checkpoints`. Runtime state is stored under:

```text
taggy-checkpoints/<private-recovery-id>/runtime.json
```

Related large-batch manifests and completed-row objects are stored below the
same private recovery-ID folder. The recovery URL is not stored as a separate
record; its `?run=` value identifies that folder. Treat the URL like a password.

Inspect the bucket in the Google Cloud console:

https://console.cloud.google.com/storage/browser/taggy-508408-checkpoints?project=taggy-508408

Public access prevention and uniform bucket-level access must remain enabled.
The service account must retain only the required bucket role,
`roles/storage.objectUser`. The one-time bucket hardening command is
`gcloud storage buckets update gs://taggy-508408-checkpoints --public-access-prevention`.
The bucket lifecycle deletes checkpoint objects after 30 days. Temporary media
inside a Cloud Run container is ephemeral and is not part of the recovery
checkpoint.

## Public access decision

Making the app public removes the Google sign-in requirement but does not make
the GCS bucket public. Provider secrets remain server-side. However, anyone who
can reach the app can trigger Cloud Run, Gemini, and Apify usage, so public
access also creates a cost-abuse risk. Before broad distribution, configure
budget alerts, retain provider quotas, and complete the staged load test below.

Do not make the service public while a live tagging run is still in progress.
Changing security or deploying a revision should happen only after current
users have saved a recovery link and completed or paused their run.

## Load-test and operating limits

Use separate browsers or devices and increase load gradually:

1. two users with 25 posts each;
2. two users with 50 posts each; and
3. only if healthy, two users with 100 posts each.

Record completion time, failed posts, retries, Cloud Run 5xx responses, instance
restarts, CPU, memory, and in-memory filesystem usage. Long request-latency
lines can represent an open Streamlit WebSocket; they do not by themselves mean
an action took that long.

The September 13 five-tab run reached roughly 50-65% CPU, 75-82% memory,
0.73-0.76 GB p95/p99 in-memory filesystem usage, and about 8-14 concurrent
requests. No 5xx, memory-limit, or checkpoint failures appeared. One stale
generated CSV media URL returned 404. This is promising for the pilot, but
memory is the current constraint. Confirm memory falls after runs finish and
tabs close before approving the two-by-100 test. If memory remains near 80%,
investigate cleanup or increase the service to 4 GiB before heavier use.

## Cost and rollback

`min-instances=0` allows the service to scale to zero when no sessions are
connected. An open Streamlit tab can keep the one instance billable. Cloud Run,
Gemini, Apify, Secret Manager, logging, and GCS have separate quotas or charges.

Rollback remains straightforward: keep the last known-good Cloud Run revision
and do not route traffic to a new revision until its health and recovery path
have been verified.
