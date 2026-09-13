# Deploy your own Taggy fork on Google Cloud

This guide is for someone who forks the Taggy GitHub repository and wants an
independent public Taggy link on their own Google Cloud account.

## What the fork does and does not copy

The fork copies the Taggy **code**.

It does not copy the original owner's:

- Gemini key or Apify token;
- Google Cloud project or billing;
- Cloud Storage recovery files;
- Continue later links; or
- Cloud Run service and settings.

The new owner must create those items in their own Google Cloud project. Their
app and charges are then separate from the original deployment.

## Before starting

The new owner needs:

1. A Google account that can create or use a Google Cloud project.
2. Billing enabled on that project. Cloud Run still has a free allowance, but
   billing must normally be linked.
3. Their own Gemini API key.
4. Their own Apify token.
5. A fork of the stable Taggy `main` branch.

Do not put API keys in GitHub, source code, screenshots, or command history.

## Step 1: Fork the repository

1. Open the Taggy repository on GitHub.
2. Click **Fork**.
3. Keep **Copy the DEFAULT branch only** selected after the approved release is
   merged into `main`.
4. Create the fork in the new owner's GitHub account.

If the owner must test before this release is merged, clear **Copy the DEFAULT
branch only** so the feature branches are included, then check out
`agent/cloud-run-fork-ready`. Waiting for the approved `main` release is the
simpler option.

## Step 2: Create or choose a Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project or choose an empty existing project.
3. Link a Cloud Billing account.
4. Open **Cloud Shell** using the terminal icon at the top of the console.

The project ID must be globally unique and cannot contain underscores. The
commands below use `their-taggy-project` as an example. Replace it once.

```bash
export TAGGY_PROJECT_ID="their-taggy-project"
export TAGGY_REGION="asia-southeast1"
export TAGGY_BUCKET="${TAGGY_PROJECT_ID}-checkpoints"
export TAGGY_SERVICE_ACCOUNT="taggy-worker@${TAGGY_PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$TAGGY_PROJECT_ID"
```

## Step 3: Enable the Google services

In Cloud Shell, run:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project="$TAGGY_PROJECT_ID"
```

## Step 4: Create Taggy's service account

```bash
gcloud iam service-accounts create taggy-worker \
  --project="$TAGGY_PROJECT_ID" \
  --display-name="Taggy worker"
```

This account belongs to the app. Website visitors do not sign in with it.

## Step 5: Add the two private provider keys

Use the Google Cloud Console so the values do not appear in shell history:

1. Open **Security > Secret Manager**.
2. Click **Create secret**.
3. Name it `taggy-gemini-api-key`, paste the new owner's Gemini key, and create
   it.
4. Create another secret named `taggy-apify-token` and paste the new owner's
   Apify token.

Then let only Taggy read those secrets:

```bash
gcloud secrets add-iam-policy-binding taggy-gemini-api-key \
  --project="$TAGGY_PROJECT_ID" \
  --member="serviceAccount:$TAGGY_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding taggy-apify-token \
  --project="$TAGGY_PROJECT_ID" \
  --member="serviceAccount:$TAGGY_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

To change either key later, add a new version to the same Secret Manager
secret. Taggy reads the mounted `latest` version, so a normal key rotation does
not require rebuilding the app. A tagging run already in progress may finish
with the old value.

## Step 6: Create private Continue later storage

```bash
gcloud storage buckets create "gs://$TAGGY_BUCKET" \
  --project="$TAGGY_PROJECT_ID" \
  --location="$TAGGY_REGION" \
  --uniform-bucket-level-access \
  --public-access-prevention
```

The app link will be public, but this bucket must stay private.

## Step 7: Download the fork

Replace `THEIR-GITHUB-NAME` below:

```bash
git clone https://github.com/THEIR-GITHUB-NAME/Content_tagging.git
cd Content_tagging
git checkout main
```

## Step 8: Add automatic recovery-file cleanup

This repository includes a rule that deletes recovery objects after 30 days:

```bash
gcloud storage buckets update "gs://$TAGGY_BUCKET" \
  --lifecycle-file=docs/gcs-checkpoint-lifecycle.json
```

Give Taggy access only to this bucket:

```bash
gcloud storage buckets add-iam-policy-binding "gs://$TAGGY_BUCKET" \
  --member="serviceAccount:$TAGGY_SERVICE_ACCOUNT" \
  --role="roles/storage.objectUser"
```

## Step 9: Deploy the public app

Run this from the cloned repository folder in Cloud Shell:

```bash
gcloud run deploy taggy \
  --source=. \
  --region="$TAGGY_REGION" \
  --project="$TAGGY_PROJECT_ID" \
  --no-invoker-iam-check \
  --service-account="$TAGGY_SERVICE_ACCOUNT" \
  --concurrency=80 \
  --max-instances=1 \
  --min-instances=0 \
  --timeout=3600 \
  --memory=2Gi \
  --cpu=2 \
  --cpu-boost \
  --session-affinity \
  --set-env-vars="CHECKPOINT_GCS_BUCKET=$TAGGY_BUCKET,CHECKPOINT_GCS_PROJECT=$TAGGY_PROJECT_ID,CHECKPOINT_GCS_PREFIX=taggy-checkpoints,APIFY_TOKEN_FILE=/var/secrets/apify/token,GEMINI_API_KEY_FILE=/var/secrets/gemini/key" \
  --set-secrets="/var/secrets/apify/token=taggy-apify-token:latest,/var/secrets/gemini/key=taggy-gemini-api-key:latest"
```

Cloud Run prints the new public `run.app` URL when deployment finishes.

Keep `--max-instances=1` for this pilot configuration. Google Cloud Storage
keeps Continue later data durable, while the per-batch execution safeguard
prevents one recovery job from running twice inside that instance. Raising the
instance limit requires a distributed execution lock first.

### Concurrent AI-tagging batches

As in the existing Taggy Google Cloud version, the app does not impose a fixed
three-job or five-job limit. Separate users may start AI-tagging batches at the
same time. Opening tabs alone does not consume provider capacity; the heavier
work begins when users start tagging. The practical limit depends on the
service's 2 CPU and 2 GiB memory allocation and on Gemini and Apify quotas, so
monitor CPU, memory, errors, latency, and provider usage during load testing.

## Choose or rename the link

### Simple option: choose the Cloud Run service name

The word after `gcloud run deploy` is the service name. For example:

```bash
gcloud run deploy taggy-mycompany ...
```

The generated address will include `taggy-mycompany`, but Google also adds a
unique suffix and `.run.app`. An existing Cloud Run service cannot be renamed
in place; deploy a new service with the preferred name instead.

### Clean option: use a domain you own

For a fully branded address such as `taggy.mycompany.com`, buy or use an
existing domain and map it to the Cloud Run service. Google recommends placing
a global external Application Load Balancer in front of Cloud Run. Direct
Cloud Run domain mapping is simpler but is still a limited Preview feature and
is not Google's recommended production option.

Keep the generated `run.app` address during the pilot. Add the custom domain
after the app and expected costs are stable. When Taggy is opened through the
custom domain, new Continue later links use that domain too.

## Step 10: Test before sharing the link

1. Open the base `run.app` URL in an Incognito or Private window.
2. Confirm that no Google sign-in appears.
3. Upload a small file with three posts.
4. Run metrics or tagging.
5. Click **Continue later** and wait for the green saved confirmation.
6. Copy the private recovery link, close the tab, and reopen that link.
7. Confirm that the batch returns.
8. Open the bucket in **Cloud Storage > Buckets > Objects**. Look under:

```text
taggy-checkpoints
  -> 32-character recovery ID
  -> runtime.json
```

Share the plain app URL. Do not publish a Continue later URL because it can
reopen that person's saved batch.

## Step 11: Add a budget alert

Open **Billing > Budgets & alerts** and create a small monthly alert. A budget
alert warns the owner; it does not automatically stop usage. Gemini and Apify
may also have separate quotas or charges.

## Safe updates after the first deployment

Do not connect automatic production deployment at first. Test every change in
a feature branch and a separate preview service.

### 1. Create a test branch

From the fork's local or Cloud Shell checkout:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b test/my-change
```

Make the change, then run the same checks used by GitHub:

```bash
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests
```

Only push the test branch:

```bash
git push -u origin test/my-change
```

Open a pull request but **do not merge it**. Wait for the GitHub `tests` check
to pass. If GitHub Actions is disabled in a new fork, enable it from the fork's
**Actions** tab first.

### 2. Deploy that branch as a separate preview

In Cloud Shell, check out the same branch:

```bash
git fetch origin
git checkout test/my-change
git pull --ff-only origin test/my-change
```

Run the Step 9 deployment command with only these two changes:

- deploy the service as `taggy-preview` instead of `taggy`;
- use `CHECKPOINT_GCS_PREFIX=taggy-preview-checkpoints` instead of
  `CHECKPOINT_GCS_PREFIX=taggy-checkpoints`.

The preview gets its own URL and recovery folder. It may reuse the same service
account and mounted Secret Manager entries, but its Gemini and Apify usage still
counts against the same provider accounts.

Confirm which preview revision is live:

```bash
gcloud run services describe taggy-preview \
  --region="$TAGGY_REGION" \
  --project="$TAGGY_PROJECT_ID" \
  --format="value(status.latestReadyRevisionName,status.url)"
```

### 3. Test the preview before approving it

1. Open the preview URL in an Incognito or Private window and confirm that no
   Google sign-in is requested.
2. Test one uploaded file and one pasted-link batch.
3. For Top Posts, check all ranking choices. Include decimal rate values such
   as 9.1% and 9.9%, and confirm 9.9% wins.
4. Test two selected ranking metrics and confirm the second metric breaks a tie
   in the first metric.
5. Test grouping and confirm Top N is selected separately for each group.
6. Run a small AI-tagging batch and a Metrics-only batch.
7. Create a Continue later link, close the tab, and reopen that private link.
8. Confirm the preview recovery object appears under
   `taggy-preview-checkpoints` in the private bucket.
9. Open several separate batches only when doing a controlled load test; watch
   Cloud Run CPU, memory, latency, 5xx responses, and provider usage.
10. Confirm the production `taggy` URL still works and was not changed.

If anything fails, fix the same feature branch, push it again, and redeploy only
`taggy-preview`. `main` and the production `taggy` service remain untouched.

### 4. Release only after approval

1. Record the preview revision that passed.
2. Merge the pull request into `main` only after explicit approval.
3. Check out the updated `main` and manually deploy `taggy` again.
4. Test the production link once more. If it fails, send traffic back to the
   previous known-good Cloud Run revision.

A GitHub change does not alter Cloud Run until a deployment is run, unless the
owner deliberately adds a Cloud Build trigger later. Cloud Run keeps older
revisions, so the owner can send traffic back to a previous revision if a new
release has a problem.

## Independence from the original Taggy deployment

This new deployment does not change the original Cloud Run or Streamlit links.
The two deployments remain independent unless both owners deliberately reuse
the same Gemini or Apify provider account, in which case those provider quotas
and charges are shared.
