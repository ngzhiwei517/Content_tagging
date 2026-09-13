# Taggy Cloud simple guide

Last checked: 13 September 2026

## What is GCS?

**GCS means Google Cloud Storage.**

Think of it as a private Google Drive folder used by Taggy.

When someone clicks **Continue later**, Taggy saves their progress as a small
file in GCS. The private recovery link tells Taggy which saved file to reopen.

GCS does not store the Gemini or Apify keys inside the recovery file. It also
does not make the saved files public.

## What does each service do?

| Service | Simple meaning |
|---|---|
| Streamlit | The Taggy screen and buttons |
| Cloud Run | The Google server running Taggy |
| GCS | The private folder saving Continue later progress |
| GitHub | Where the Taggy code is kept |
| Supabase | The previous recovery storage; not active in the current Cloud Run setup |
| Gemini | Performs AI tagging |
| Apify | Helps collect post information when direct collection fails |
| Secret Manager | Safely stores the Gemini and Apify keys |

Taggy still uses Streamlit, but it now runs on Cloud Run instead of relying only
on Streamlit Community Cloud. GCS is now the main recovery storage instead of
Supabase.

## Should we use the Cloud Run link?

**Yes, I recommend Cloud Run for the pilot.**

The five-tab test worked and no server or checkpoint errors were found. Cloud
Run also gives us better performance information and control than Streamlit
Community Cloud.

Keep the old Streamlit link temporarily as a backup. Do not remove it yet.

The only concern is memory. During the test, memory reached about 75-82%. We
should check whether it falls after the runs finish and the tabs are closed.

## What should we do next?

1. Finish or pause the current tests and save the Continue later links.
2. Close the test tabs and wait 10-15 minutes.
3. Check the Cloud Run memory graph again.
4. If memory falls, turn on the prepared new version.
5. Test one small batch and one Continue later link.
6. Keep the spending alert active and confirm the public link in an Incognito window.
7. Test two people with 25 posts each before testing larger batches.

## What happens when GitHub changes?

- The old Streamlit Community app may update automatically when its connected
  GitHub branch changes.
- Cloud Run does **not** update automatically right now. We must deploy the
  approved change manually.
- Automatic Cloud Run deployment can be added later, after we decide which
  GitHub branch is the final branch.

The prepared Cloud Run version can read the newest Apify key from Secret
Manager. After that version is active, replacing the Apify key will not require
another app deployment. A tagging run already in progress will continue using
the key it started with.

## Is Cloud Run slower because it has a free version?

No. Cloud Run is a real Google-managed server. It charges based on usage and
also gives a monthly free allowance.

The app can become slower when many people use it together because our current
setup deliberately uses one Taggy server instance. Everyone shares its 2 CPU
and 2 GiB memory. Five tabs worked, but we have not yet proved the maximum safe
number of users.

## Is it more reliable than Streamlit plus Supabase?

For this pilot, yes:

- GCS did not show the Supabase save-timeout problem.
- Continue later data is stored privately.
- Cloud Run gives us error logs, CPU and memory graphs, and easy rollback.
- The observed test had no server failures.

It is still a pilot, not an unlimited production system. A restart can interrupt
the screen, but saved work can be reopened using the Continue later link.

## Can we change the link name?

We cannot rename the existing generated `run.app` address.

Later, we can connect a domain we own, for example:

```text
taggy.yourcompany.com
```

For now, keep the existing Cloud Run address until testing is complete.

## Will a new account affect the old Streamlit link?

No.

- Adding another Google account to Cloud Run affects only Cloud Run.
- Making Cloud Run public affects only the Cloud Run link.
- The old Streamlit link remains separate and can stay available as backup.

Both links may still share Gemini or Apify usage if they use the same provider
account.

## Where is Continue later data stored?

[Open the private Taggy storage folder](https://console.cloud.google.com/storage/browser/taggy-508408-checkpoints?project=taggy-508408)

Then open:

```text
taggy-checkpoints
  -> your 32-character recovery ID
  -> runtime.json
```

The recovery ID is the value after `?run=` in the Continue later link. Keep it
private because the link can reopen that batch.

## Will storage become full?

You do not need to delete anything now.

- Current usage is only about **103 MB**.
- Google Cloud Storage can hold far more than this.
- Taggy automatically deletes recovery files after 30 days.
- Deleted files remain recoverable for seven more days.

Do not manually delete a recovery folder that someone still needs. Its Continue
later link would stop working.

## Useful links

- [Taggy Cloud Run performance](https://console.cloud.google.com/run/detail/asia-southeast1/taggy-web-latest-test/metrics?project=taggy-508408)
- [Taggy Cloud Run errors and logs](https://console.cloud.google.com/run/detail/asia-southeast1/taggy-web-latest-test/logs?project=taggy-508408)
- [Taggy Continue later storage](https://console.cloud.google.com/storage/browser/taggy-508408-checkpoints?project=taggy-508408)

## Current status in one sentence

The Cloud Run base link is public, its Continue later data is private in GCS,
and the current pilot remains intentionally limited to one app instance.
