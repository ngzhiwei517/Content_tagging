# Set up a public Taggy test

This guide creates a Taggy link that anyone can open without Google sign-in.

## Best choice for you

You do **not** need another Google Cloud project.

Because your project limit is full, create a second Cloud Run service inside
the existing `taggy-508408` project.

Suggested names:

- Cloud Run service: `taggy-test-public`
- Recovery bucket: `taggy-508408-taggy-test-checkpoints`

This creates a new public URL. It does not replace or change:

- the current `taggy-web-latest-test` Cloud Run service; or
- the old Streamlit Community Cloud link.

## Part A: Recommended same-project setup

### Step 1: Create a separate recovery bucket

1. Open [Cloud Storage](https://console.cloud.google.com/storage/browser?project=taggy-508408).
2. Click **Create**.
3. Enter `taggy-508408-taggy-test-checkpoints`.
4. Choose **Singapore (`asia-southeast1`)**.
5. Choose **Standard** storage.
6. Turn on **Uniform bucket-level access**.
7. Keep **Public access prevention** enabled.
8. Create the bucket.

The bucket must remain private even though the Taggy app is public.

### Step 2: Add automatic cleanup

1. Open the new bucket.
2. Open **Lifecycle**.
3. Click **Add a rule**.
4. Choose **Delete object**.
5. Choose the condition **Age**.
6. Enter `30` days.
7. Save the rule.

Old Continue later files will then clean themselves up automatically.

### Step 3: Give Taggy access to the bucket

This is an internal Google permission. App users still do not need to sign in.

1. Open the bucket's **Permissions** tab.
2. Click **Grant access**.
3. Enter:

   `taggy-worker@taggy-508408.iam.gserviceaccount.com`

4. Select **Storage Object User**.
5. Save.

### Step 4: Deploy the public service

Run the following command from the approved Taggy feature-branch folder. It
uses the existing Gemini and Apify secrets but saves recovery data in the new
test bucket.

```bat
gcloud run deploy taggy-test-public --source=. --region=asia-southeast1 --project=taggy-508408 --no-invoker-iam-check --service-account=taggy-worker@taggy-508408.iam.gserviceaccount.com --concurrency=80 --max-instances=1 --min-instances=0 --timeout=3600 --memory=2Gi --cpu=2 --cpu-boost --session-affinity --set-env-vars="CHECKPOINT_GCS_BUCKET=taggy-508408-taggy-test-checkpoints,CHECKPOINT_GCS_PROJECT=taggy-508408,CHECKPOINT_TABLE=batch_checkpoint_objects,APIFY_TOKEN_FILE=/var/secrets/taggy/apify-token" --set-secrets="GEMINI_API_KEY=taggy-gemini-api-key:latest,/var/secrets/taggy/apify-token=taggy-apify-token:latest"
```

`--no-invoker-iam-check` means visitors can open the app without signing in.

### Step 5: Test the public link

1. Copy the new `run.app` URL shown after deployment.
2. Open it in an Incognito or Private window.
3. Confirm that Google sign-in does not appear.
4. Upload a small file with three posts.
5. Run tagging or metrics.
6. Click **Continue later** and copy the private recovery link.
7. Close the tab.
8. Open the recovery link and confirm the batch returns.
9. Open the new GCS bucket and confirm that its `taggy-checkpoints` folder
   contains a recovery-ID folder and `runtime.json`.

Do not share the recovery link publicly. The base app URL is public, but each
recovery link should remain private.

### Step 6: Add a spending alert

1. Open [Billing budgets](https://console.cloud.google.com/billing/budgets?project=taggy-508408).
2. Create a budget for the `taggy-508408` project.
3. Choose a small monthly amount that you are comfortable monitoring.
4. Keep email alerts at 50%, 90%, and 100%.

A budget alert sends warnings; it is not automatically a hard spending limit.
Gemini and Apify also have their own usage and charges.

### Step 7: Test gradually

1. One user with three posts.
2. Two users with ten posts each.
3. Two users with 25 posts each.
4. Check CPU and memory.
5. Only then try 50 or 100 posts per user.

The current setup uses one Cloud Run instance. More users share the same 2 CPU
and 2 GiB memory.

## Part B: Using another Google account

Another Google account may be able to create a project if that account still
has project quota. It also needs Cloud Billing before Cloud Run can be used.

Important points:

- The project display name can be `taggy_test`.
- The project ID cannot contain an underscore. Use something such as
  `taggy-test-12345`.
- The new account owns the new project and billing setup.
- Your current Google account cannot manage it unless access is granted or you
  switch accounts.
- A completely new project needs its own APIs, service account, secrets, bucket,
  permissions, and deployment.
- It does not affect the current Streamlit or Cloud Run links.
- If it uses the same Cloud Billing account, the Cloud Run free allowance is
  shared across that billing account; a new project does not reset it.
- If both projects use the same Gemini or Apify accounts, they still share those
  provider quotas and costs.

Using another account only to avoid the project limit adds more setup and makes
ownership harder. Google also allows a project-quota increase request. For this
test, a second service inside `taggy-508408` is simpler.

## If you still want a completely separate project

Complete these steps in the new account:

1. Create a project with a unique ID such as `taggy-test-12345`.
2. Link a Cloud Billing account.
3. Enable Cloud Run, Cloud Build, Artifact Registry, Cloud Storage, and Secret
   Manager APIs.
4. Create a `taggy-worker` service account.
5. Create a private Singapore GCS bucket with a 30-day delete rule.
6. Grant the service account **Storage Object User** on that bucket.
7. Create `taggy-gemini-api-key` and `taggy-apify-token` in Secret Manager.
8. Grant the service account **Secret Manager Secret Accessor** on those two
   secrets.
9. Deploy the Taggy source using the same settings as Part A, replacing every
   project ID, bucket name, and service-account address with the new values.
10. Select public access or use `--no-invoker-iam-check`.
11. Test in an Incognito window.
12. Create a billing budget alert.

Never place Gemini or Apify keys directly in GitHub, source code, screenshots,
or deployment commands. Enter their values only through Secret Manager.

## What happens after GitHub changes?

This public test will still use manual deployment at first. A GitHub push will
not change Cloud Run until someone deploys the reviewed code again.

Automatic deployment can be connected later after the correct GitHub branch is
chosen and protected.

## Simple summary

The recommended setup is:

```text
Existing project: taggy-508408
    -> Current private service stays unchanged
    -> New public service: taggy-test-public
    -> New private recovery bucket
    -> Existing protected Gemini and Apify secrets
```

This avoids the project-limit problem and gives you a separate public link for
testing.
