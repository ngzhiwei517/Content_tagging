# UGC Content Tagging Platform

A Streamlit application for tagging, reviewing, and reporting TikTok and Instagram Reels content for music-marketing workflows.

[Open the Streamlit app](https://umgcontenttag.streamlit.app/)

## Key capabilities

- Upload multiple CSV/XLSX files or paste TikTok and Instagram post links.
- Combine both platforms in one batch with duplicate-link detection.
- Collect public metadata through direct retrieval first, with selective Apify fallback.
- Classify creative types with Gemini multimodal analysis and reusable guardrails.
- Route uncertain results to human review before export.
- Compare creative, market, track, post, and creator performance.
- Export marketing-ready CSV/XLSX reports and an internal QA workbook.

## Workflow

```text
Add posts -> Select posts -> Run tagging -> Review -> Dashboard and export
```

The app supports **Top posts** and **Tag every link**. If selected posts or creator profiles are unavailable, it continues through the ranked list to return the requested number whenever enough valid records exist.

## Inputs

- **Post link:** required for every row.
- **Track name:** required and automatically suggested from uploaded filenames when possible.
- **Artist:** optional; Apple Music/iTunes lookup can identify the artist from the track name.
- **Market:** optional; read from the file or filename when available, otherwise grouped as `Other` in summaries.

For best results, use direct post URLs:

- TikTok: `https://www.tiktok.com/@creator/video/123...`
- Instagram: `https://www.instagram.com/reel/SHORTCODE/`

Shortened, private, deleted, profile, hashtag, and Story links may not be available. See [Link compatibility](docs/LINK_COMPATIBILITY.md).

## Tagging and recovery

The default model is **Gemini 3.1 Flash-Lite**. The app starts with metadata and cover evidence, then checks additional frames or the full video only when required.

Large batches are processed in protected chunks and saved after each completed result. Interrupted jobs resume from the first unfinished post without repeating completed Gemini analysis.

Checkpoints are local by default. Supabase/Postgres can optionally provide recovery after an app restart or redeployment. Checkpoints never contain provider credentials or downloaded media. See [Persistent checkpoints](docs/PERSISTENT_CHECKPOINTS.md).

## Creator performance

The dashboard can enrich up to 100 ranked creators using public activity from the latest three months. It:

- uses direct public retrieval before any paid fallback;
- resolves a changed TikTok username from an existing post when possible;
- replaces unavailable profiles with the next-ranked available creators; and
- keeps profile metrics separate from the current batch metrics.

Instagram profile metrics may use a limited Apify fallback when direct public data is incomplete.

## Configuration

Store deployment credentials in Streamlit Secrets:

```toml
GEMINI_API_KEY = "replace-with-the-deployment-key"
APIFY_TOKEN = "replace-with-the-deployment-token"
```

Never commit real credentials. For local use, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add the values there.

## Run locally

Python 3.11-3.14 is supported.

### Windows

Double-click `run_windows.bat`, or run:

```bat
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS

```bash
chmod +x run_mac.command
./run_mac.command
```

The app opens at `http://localhost:8501`.

## Outputs

- Marketing CSV with one row per post.
- Excel workbook with `All Posts` and market sheets when market data exists.
- Internal Review / QA workbook with model and validation details.

Unavailable metrics are shown as `Not available`, not as confirmed zeroes.

## Tests

```bash
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests
```

## Documentation

- [Documentation index](docs/README.md)
- [Maintainer handover](docs/HANDOVER.md)
- [Code map](docs/CODE_MAP.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Changelog](CHANGELOG.md)

## Privacy

Do not commit API keys, campaign data, exports, or downloaded media. The application processes public social content and is not affiliated with TikTok, Instagram, Google, Apple, or Apify.
