# UGC Content Tagging Platform

Streamlit application for selecting, tagging, reviewing and reporting TikTok and Instagram Reels content for music-marketing workflows.

[Open the stable Streamlit demo](https://umgcontenttag.streamlit.app/)

> The public demo remains the validated TikTok release. Instagram Reels support is available in the current local candidate and should be treated as a directional pilot until separately validated.

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

## Models

- **Gemini 3.1 Flash-Lite** — recommended default
- **Gemini 3.5 Flash** — slower optional analysis

The app analyses the cover and metadata first, then checks additional frames or the full video only when needed. A narrow evidence verifier handles suspicious contradictions; genuinely unclear posts remain in human review.

## Run locally

### Windows

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Or double-click `run_windows.bat`.

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

## Documentation

- [Documentation index](docs/README.md)
- [Code map](docs/CODE_MAP.md)
- [Project context](docs/PROJECT_CONTEXT.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Changelog](CHANGELOG.md)

## Tests

```bash
python -m py_compile app.py final_update2_adapter.py final_update2_backend.py final_update2_backend_source.py instagram_reels_adapter.py model_comparison.py review_routing.py
python -m unittest discover -s tests -v
```

## Privacy

Do not commit API keys, campaign data, exports or downloaded media. Credentials entered in the app remain in Streamlit session state. The project uses publicly available social content and is not affiliated with TikTok, Instagram, Google or Apify.
