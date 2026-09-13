# Taggy Cloud operations guide

Last verified: 13 September 2026, Singapore time

This document explains what currently runs Taggy, what happens after a GitHub
change, where recovery data is stored, how to change the app address, and what
to check before opening the app to everyone.

## Recommended next step

Use Cloud Run and Google Cloud Storage (GCS) for the pilot, while keeping the
existing Streamlit Community Cloud deployment available as a short-term
rollback.

Before making the Cloud Run URL public:

1. Finish or pause the current test runs and save their **Continue later** links.
2. Close the test tabs and wait 10-15 minutes.
3. Confirm Cloud Run memory and in-memory filesystem usage fall from the test
   peak. If memory remains near 80%, increase memory to 4 GiB or investigate
   temporary-file/session cleanup before a heavier test.
4. Move main traffic from revision `00007-kv9` to the staged, healthy revision
   `00008-wij` and run one small upload, tagging, and recovery test.
5. Configure a Google Cloud billing budget alert, then disable IAP and allow
   unauthenticated access if a no-sign-in public URL is still required.
6. Test two users with 25 posts each, then 50 each, before trying 100 each.

## Current resource snapshot

### Cloud Run application

- Project: `taggy-508408`
- Region: Singapore (`asia-southeast1`)
- Service: `taggy-web-latest-test`
- Main URL: `https://taggy-web-latest-test-jm5fktzloq-as.a.run.app`
- Authentication: Google IAP is currently enabled; the app is not public yet.
- Live revision: `taggy-web-latest-test-00007-kv9`, receiving 100% of main
  traffic.
- Staged revision: `taggy-web-latest-test-00008-wij`, healthy, with a private
  `hot-secrets-test` tag and 0% of main traffic.
- Capacity: maximum one instance, minimum zero instances, 2 vCPU, 2 GiB memory,
  concurrency 80, 3,600-second request timeout, and session affinity.
- Automatic GitHub deployment: disabled; no Cloud Build trigger exists.
- Errors checked after the five-tab test: no HTTP 5xx responses.

Open the service:

- [Cloud Run metrics](https://console.cloud.google.com/run/detail/asia-southeast1/taggy-web-latest-test/metrics?project=taggy-508408)
- [Cloud Run logs](https://console.cloud.google.com/run/detail/asia-southeast1/taggy-web-latest-test/logs?project=taggy-508408)
- [Cloud Run revisions](https://console.cloud.google.com/run/detail/asia-southeast1/taggy-web-latest-test/revisions?project=taggy-508408)

### Recovery storage

- Bucket: `taggy-508408-checkpoints`
- Location: Singapore
- Storage class: Standard
- Current usage: approximately 102.8 MB
- Public access prevention: enforced
- Uniform bucket-level access: enabled
- Taggy service-account role: `roles/storage.objectUser`
- Automatic lifecycle deletion: after 30 days
- Soft-delete recovery after deletion: seven days

[Open the checkpoint bucket](https://console.cloud.google.com/storage/browser/taggy-508408-checkpoints?project=taggy-508408)

Objects are arranged like this:

```text
taggy-checkpoints/
  <32-character-private-recovery-id>/
    runtime.json
    jobs/
      ...large-batch progress objects...
```

`<32-character-private-recovery-id>` is a placeholder. The actual folder name
matches the value after `?run=` in a Continue later link. The link itself is not
stored as a separate object. Anyone who has that recovery link can attempt to
reopen the batch, so do not post it publicly.

## What happens when GitHub changes?

Cloud Run and Streamlit Community Cloud currently behave differently:

- **Cloud Run:** a GitHub push does nothing automatically right now. Someone
  must run the reviewed Cloud Run deployment command. A deployment creates a
  new immutable revision; traffic can remain on the old revision until the new
  one is tested.
- **Streamlit Community Cloud:** it remains connected to its configured GitHub
  repository and branch, so commits to that branch can update the existing
  Streamlit URL independently.
- **Secret rotation:** after revision `00008-wij` becomes live, adding a new
  version to `taggy-apify-token` does not require an app redeployment. New
  metrics/tagging actions read the mounted `latest` secret. An action already
  running continues with the key it loaded at the beginning.

Do not enable automatic Cloud Run deployment until the accepted source branch
and deployment settings are documented. When enabled later, Cloud Run can use a
Cloud Build trigger to build and deploy every push to one selected branch.

## Current limitations and reliability

### Compared with Streamlit Community Cloud plus Supabase

Cloud Run plus GCS is the preferred pilot setup because:

- CPU and memory are explicitly configured instead of relying on Community
  Cloud's shared free-app allowance.
- GCS stores recovery checkpoints as private objects and has already passed a
  real write/read/delete check.
- The observed five-tab test window showed no 5xx, checkpoint, or memory-limit
  errors.
- It avoids the Supabase statement-timeout problem previously seen during
  checkpoint verification.
- Cloud Logging, metrics, immutable revisions, and traffic rollback are
  available in one place.

It is not unlimited or a full production multi-user system:

- Taggy still runs as one Streamlit frontend process. The service is capped at
  one instance because Streamlit upload and generated-download sessions broke
  when requests were split across instances.
- All simultaneous users share the same 2 vCPU and 2 GiB container.
- The observed five-tab test used roughly 50-65% CPU and peaked around 75-82%
  memory. Memory, not the configured request count, is the current constraint.
- `80 concurrent requests` does not mean 80 users or 80 actions per second. A
  browser holds a long-lived WebSocket and can make additional upload/download
  requests.
- Gemini and Apify have their own quotas, latency, availability, and charges.
- A container restart can interrupt the screen session. The private Continue
  later link is the recovery mechanism for saved work.
- There is no app-level public-user rate limit, per-user quota, job queue,
  Cloud Armor policy, or administrative dashboard yet.

Cloud Run is a managed serverless service, not a weaker "free server." It is
pay-as-you-go with a monthly free-tier discount. More users can still make the
app slower because this particular deployment deliberately uses one instance,
and an open Streamlit WebSocket can keep that instance active and billable.

## What does Taggy currently use?

| Component | Current purpose | Current status |
|---|---|---|
| Streamlit | User interface and session workflow | Still used inside Cloud Run |
| Cloud Run | Hosts the Streamlit container | Pilot host |
| Google Cloud Storage | Private Continue later checkpoints | Primary recovery store |
| Supabase | Previous database checkpoint option | Configured only as rollback; GCS takes precedence |
| Secret Manager | Stores Gemini, Apify, and rollback credentials | Active |
| Gemini | AI classification and Taggy open-ended answers | Active when AI tagging requires it |
| Apify | Paid fallback when direct public retrieval is insufficient | Active selectively |
| GitHub | Source-code repository | Active; not auto-deploying to Cloud Run |
| Cloud Build / Artifact Registry | Builds and stores Cloud Run container images | Used during manual deployment |
| Cloud Logging and Monitoring | Errors, requests, CPU, memory, and latency | Active |
| Identity-Aware Proxy | Restricts the Cloud Run URL to allowed Google accounts | Active for now |

## Will a new account or Cloud setup affect the Streamlit link?

No, not by itself.

- Adding another Google account to IAP changes only who can open the Cloud Run
  URL. It does not alter the Streamlit Community Cloud URL.
- Making Cloud Run public removes the Cloud Run sign-in screen only. The old
  Streamlit deployment remains separate.
- Creating the service in a different Google Cloud project creates different
  resources and normally a different `run.app` URL.
- Both deployments can still share provider quota or cost if they use the same
  Gemini or Apify account.
- A GitHub commit can affect Streamlit Community Cloud if it watches that
  branch, while Cloud Run remains unchanged until manually deployed.

Keep the Streamlit URL as rollback during acceptance testing. Stop sharing it
only after Cloud Run upload, tagging, export, and Continue later recovery have
all been accepted.

## How to change the link name

The existing Cloud Run service name cannot be renamed. The default `run.app`
hostname therefore cannot be edited into a custom friendly name.

Available options:

1. **Recommended for the pilot:** keep the current `run.app` URL until the
   deployment is accepted.
2. **Recommended friendly address:** use a domain you own, such as
   `taggy.example.com`, in front of the existing service. Google recommends a
   global external Application Load Balancer for a production custom domain.
3. **New Cloud Run service:** deploy under another service name. This produces
   another generated `run.app` URL and duplicates service configuration.

Do not use a public URL-shortening service for a Continue later link because
the private recovery ID may be recorded by the shortening provider. A custom
domain is safe for the base app URL; the `?run=` recovery value must still stay
private.

## Storage capacity and deletion

The bucket does not have a small fixed capacity like a free database plan.
Cloud Storage scales with usage; an individual object can be up to 5 TiB. Taggy
currently uses only about 102.8 MB.

Manual deletion is not required because the lifecycle rule automatically
deletes checkpoint objects after 30 days. Deleted objects are currently kept in
soft-delete state for seven additional days so accidental deletion can be
recovered. Soft-deleted data can still incur storage charges.

Do not delete an active recovery-ID folder: its Continue later link will stop
working. If the retention period needs to be shorter later, update the lifecycle
rule rather than manually clearing the whole bucket.

## Routine checks

During a load test, inspect:

- Cloud Run **Metrics**: CPU, memory, in-memory filesystem, instance count, and
  max concurrent requests;
- Cloud Run **Logs**: HTTP 5xx, `Traceback`, memory-limit messages, checkpoint
  errors, Gemini quota messages, and Apify failures;
- Cloud Storage **Objects**: verify a recovery folder contains `runtime.json`;
- Billing **Budgets & alerts**: watch Cloud Run and provider spending.

Long request-latency lines can be normal Streamlit WebSockets. Treat failures,
container restarts, sustained high memory, or users making no progress as the
important warning signs.

## Official references

- [Cloud Run pricing and free tier](https://cloud.google.com/run/pricing)
- [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)
- [Cloud Run continuous deployment](https://docs.cloud.google.com/run/docs/continuous-deployment)
- [Cloud Run custom domains](https://docs.cloud.google.com/run/docs/mapping-custom-domains)
- [Cloud Storage quotas and limits](https://docs.cloud.google.com/storage/quotas)
- [Cloud Storage soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
