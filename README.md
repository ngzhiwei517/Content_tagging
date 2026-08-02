# UGC Content Tagging Platform

Streamlit application for selecting, tagging, reviewing and reporting TikTok and Instagram Reels content for music-marketing workflows.

[Open the stable Streamlit demo](https://umgcontenttag.streamlit.app/)

> TikTok and Instagram Reels now use one shared workflow. TikTok retains its established validation baseline; Instagram tagging has encouraging directional pilot results but does not yet have a formal large-sample benchmark.

## What it does

- accepts CSV/XLSX uploads and pasted TikTok or Instagram links;
- collects public post metadata through Apify;
- classifies posts with Gemini using a shared creative-type taxonomy;
- applies reusable guardrails and routes uncertain cases to human review;
- exports marketing-ready CSV/XLSX files and an internal QA report.

## Workflow

```text
Add posts → Select posts → Run tagging → Review → Summary → Export
```

TikTok and Instagram rows can share one batch, review queue and export. Market and Track are optional. Unavailable posts are removed automatically.

### Large batches

For `Tag every link` selections above 50 posts, the app collects public data in
50-post chunks and saves each post immediately after its tagging result is
complete. Successful chunks advance automatically; users do not need to select
**Resume tagging** after every 50 posts. If API quota, a browser disconnect or
a provider interruption stops the job, reopen the same app URL and select
**Resume tagging** once the interruption is resolved. The app restarts at the
first unfinished post; completed Gemini analysis is not repeated.

If one individual post cannot be analysed while the providers remain available,
that post is sent to Human Review and the rest of the batch continues.

Checkpoints are always written to temporary files on the current app instance.
An app owner may optionally mirror the secret-free workflow and tagging objects
to Supabase/Postgres so a redeploy or replacement container can restore them.
Without that configuration, local files continue to protect ordinary reruns and
reconnects. Each batch has a private recovery link available from **Save this
batch**; users normally bookmark or copy that link instead of handling an ID. See
[`docs/PERSISTENT_CHECKPOINTS.md`](docs/PERSISTENT_CHECKPOINTS.md).

### Deployment-managed API access

A deployment owner can store the shared provider credentials in Streamlit
Secrets so users do not need to enter them:

```toml
GEMINI_API_KEY = "replace-with-the-deployment-key"
APIFY_TOKEN = "replace-with-the-deployment-token"
```

Add these values in the Streamlit deployment settings, never in GitHub. The app
opens directly on **Add Posts** and reads both credentials in the background. If
quota becomes unavailable, completed posts remain saved and the app asks the
user to contact the owner before resuming. After rotating a deployment secret,
reboot the hosted app so the next run reads the new value.

For local maintenance, place the same two values in an uncommitted
`.streamlit/secrets.toml` file. Credentials are never written to runtime or
tagging checkpoints.

## Supported post links

For the most reliable scraping, paste the direct post URL:

- TikTok: `https://www.tiktok.com/@creator/video/123...` or `/photo/123...`
- Instagram: `https://www.instagram.com/reel/SHORTCODE/` or `/p/SHORTCODE/`

Links without `www`, links with tracking parameters and full TikTok links using `http` were accepted in the compatibility test. TikTok redirect/share links (`vt.tiktok.com`, `vm.tiktok.com`, `/t/`), legacy TikTok `/v/` links and Instagram `/share/reel/` links are not reliable in the deployed app. Open those links in a browser and copy the final direct post URL before adding them.

Creator profiles, Live pages, hashtag/explore pages and Instagram Stories are intentionally rejected because they are not individual posts. See [Link compatibility](docs/LINK_COMPATIBILITY.md) for the tested matrix and limitations.

## Models

- **Gemini 3.1 Flash-Lite** — recommended default
- **Gemini 3.5 Flash** — slower optional analysis

The app analyses the cover and metadata first, then checks additional frames or the full video only when needed. A narrow evidence verifier handles suspicious contradictions; genuinely unclear posts remain in human review.

## Run locally

### Windows

```bat
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Or double-click `run_windows.bat`. The launcher prefers Python 3.14 and can
fall back to Python 3.13 or 3.11 when necessary.

### macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Or run:

```bash
chmod +x run_mac.command
./run_mac.command
```

## Outputs

- marketing CSV;
- Excel workbook with `All Posts` and market sheets;
- internal Review / QA workbook with model, review and validation details.

Public Instagram metrics depend on what the selected Apify actor and Instagram expose. Missing Shares or Saves are shown as `Not available`, never as confirmed zeroes.

## Maintaining the app

Start with the [code map](docs/CODE_MAP.md) before changing the application.
The active runtime path is:

```text
app.py
  → ugc_tagger/final_update2_adapter.py
    → ugc_tagger/final_update2_backend.py
      → ugc_tagger/final_update2_backend_source.py
```

- Keep `app.py` focused on the Streamlit workflow, session state and presentation.
- Change shared TikTok/Instagram input or output mapping in the adapter modules.
- Change prompts and reusable tagging guardrails in the backend, with focused
  regression tests.
- Change human-review decisions in `ugc_tagger/review_routing.py`.
- Do not duplicate tagging logic inside `app.py`.

Historical version suffixes remain on some helpers because tests and integration
code may depend on them. Avoid renaming working functions only for style.

## Documentation

- [Documentation index](docs/README.md)
- [Technical maintainer handover](docs/HANDOVER.md)
- [Code map](docs/CODE_MAP.md)
- [Project context](docs/PROJECT_CONTEXT.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Link compatibility](docs/LINK_COMPATIBILITY.md)
- [Changelog](CHANGELOG.md)

## Keeping your local copy updated

After the first clone, run `git pull origin main` whenever the main repository
is updated. You do not need to clone the repository again.

If you cloned your own fork, sync the fork with the upstream repository first,
then pull the updated `main` branch into your local copy.

## Tests

```bash
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests -v
```

## Privacy

Do not commit API keys, campaign data, exports or downloaded media. Credentials entered in the app remain in Streamlit session state. The project uses publicly available social content and is not affiliated with TikTok, Instagram, Google or Apify.
