# TikTok UGC Content Tagging Platform

An AI-assisted Streamlit application for selecting, tagging, reviewing and reporting TikTok user-generated content for music marketing workflows.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.59.1-red)
![Google Gemini](https://img.shields.io/badge/Google-Gemini_AI-blue)
![Apify](https://img.shields.io/badge/Apify-TikTok_Scraper-green)
![Release](https://img.shields.io/badge/Release-v68.8-purple)

## Overview

Marketing teams often need to review hundreds of TikTok posts across tracks and markets. This tool brings the full workflow into one place:

- upload generic post CSV/XLSX files or paste TikTok links;
- select every post or rank the Top N posts;
- collect current TikTok metadata through Apify;
- classify creative content with Gemini multimodal analysis;
- apply global, semantic, market and Knowledge Base guardrails;
- route uncertain posts to human review;
- explore marketing performance in an interactive dashboard;
- export clean campaign files and an internal QA report.

The product is designed for marketing users rather than technical analysts, with a guided six-step interface and concise controls.

## Key features

### Flexible post input

- Upload one or more CSV/XLSX post files.
- Paste TikTok links directly into the same batch.
- Process files from different sources as long as a TikTok link is available.
- Detect common Link, Market, Track and metric columns automatically.
- Deduplicate posts by TikTok video ID or normalized URL.
- Keep Market and Track optional.

### Top-post selection

- Tag every link in source order or select Top N posts.
- Rank by Views, Total Engagement or original file order.
- Group Top N selections by Market, Track, Source or a combined group.
- Apply one shared viral date or a separate date for each track.
- Leave individual non-viral tracks unfiltered.
- Replace unavailable or sensitive Top N posts with the next eligible ranked post automatically.
- Return the available count when a date window contains fewer than N eligible posts.

### TikTok metadata collection

The built-in Apify integration can retrieve:

- post availability and media previews;
- Views, Likes, Comments, Shares and Saves;
- creator name, followers and market context;
- captions, hashtags, post dates and music information.

Country-specific follower thresholds are used to derive KOL Size when the required market and follower data are available.

### Progressive AI tagging

The application uses evidence progressively instead of relying on a single cover image:

1. Cover image, caption, hashtags and metadata.
2. Three sampled video frames when the first result is unresolved.
3. Nine sampled frames for additional temporal evidence.
4. Full-video analysis only when earlier evidence remains insufficient.
5. Human review for unresolved, ambiguous or quality-audit cases.

After Gemini analysis, the result passes through reusable global guardrails, semantic consistency checks, the optional Creative Knowledge Base, market rules and final validation.

### Creative output

Each tagged post can include:

- Narrative;
- up to two Creative Types;
- Content Details;
- confidence and validation details for internal QA;
- a human-review reason when intervention is required.

Supported Creative Types include Dance, Lip Sync, Carousel, Relationship, Beauty, Fashion, POV, Comedy, Travel, Gaming, Fitness, Celebrity Edits, Movie/TV/Drama Edits, Reflection, Quotes, Lyrics, Lyrics Translation, Media/Infotainment, Cover, Remix and Others.

Blank AI labels are converted to `Others` rather than exported as empty values.

### Human review

The Review page allows a user to:

- inspect the post preview, caption, creator, market, track and metrics;
- open the original TikTok post;
- keep, edit or remove a flagged result;
- edit Narrative, Creative Type and Content Details;
- request an additional AI suggestion;
- preserve the original automated labels separately from final approved labels.

Unavailable, private, deleted and sensitive posts are removed automatically rather than sent to normal human review.

### Marketing dashboard

The Summary page focuses on actionable campaign information:

- total Posts, Views, Engagements and Engagement Rate;
- Creative Type mix and Views by Creative Type;
- Market Summary;
- Track Summary;
- KOL Size performance;
- top-performing posts;
- filters for the current reporting view.

User-facing reports consistently use **Views**, not Plays.

## Workflow

```text
Add post files or TikTok links
              |
              v
Select Top posts or Tag every link
              |
              v
Apify metadata and availability checks
              |
              v
Gemini multimodal tagging
              |
              v
Guardrails + Knowledge Base + validation
              |
              v
Human review when required
              |
              v
Marketing dashboard and exports
```

The interface presents this as six steps:

1. API Keys
2. Add Posts
3. Select Posts
4. Run Tagging
5. Review
6. Summary & Export

## Exports

### Final CSV

A flat marketing table containing post context, engagement metrics, Narrative, final Creative Type and Content Details.

### Grouped XLSX

Contains `All Posts` plus one worksheet per market when market values are available. Source remains a normal column rather than creating separate source tabs.

### Review / QA Report

An internal audit workbook containing attempted rows, confidence, analysis tier, validation status, review reason and label history. Important audit fields include:

- `Original AI Labels` - the automated recommendation after guardrails;
- `Final Labels` - the operational result after review;
- `Human Reviewed` - whether a reviewer completed an action;
- `Human Edited` - whether the approved labels differ from the automated labels;
- `Label History` - ordered automated and human-review events.

These fields support separate reporting of automated performance and final human-assisted workflow performance.

## Validation

On the locked blind Core-100 test, 100 posts were processed and 93 were available for evaluation:

| Metric | Result |
|---|---:|
| Correctly excluded posts | 7 |
| Exact top-two agreement with the legacy single-label benchmark | 73.1% |
| Conservative adjudicated semantic acceptance | 95.7% |
| Clear-error rate | 2.2% |
| Human-review rate | 9.7% |

The 95.7% figure describes the **final human-assisted workflow**, not pure AI-only accuracy. See [docs/VALIDATION.md](docs/VALIDATION.md) for the methodology, interpretation and approved reporting language.

## Requirements

- Python 3.11 recommended
- Google Gemini API key
- Apify API token

Keys entered in the interface are kept in Streamlit session state and are not written to project files.

## Run on Windows

Open Command Prompt in the repository folder and run:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Alternatively, double-click `run_windows.bat` after Python is installed.

## Run on macOS

Open Terminal in the repository folder and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

These commands do not require activating the virtual environment.

## Technology stack

- Python and Streamlit
- Pandas and OpenPyXL
- Plotly
- Google Gemini API
- Apify TikTok Scraper
- OpenCV, NumPy and Pillow

## Project structure

- `app.py` - Streamlit workflow, selection, review, dashboard and exports
- `final_update2_adapter.py` - schema normalization and label-audit fields
- `final_update2_backend.py` - import-safe backend loader
- `final_update2_backend_source.py` - scraping, Gemini and guardrail pipeline
- `review_routing.py` - evidence-based escalation and review routing
- `accuracy_metrics.py` - validation scoring helpers
- `creative_knowledge/` - approved reusable tagging patterns
- `tests/` - unit and product-contract tests
- `docs/` - product context, validation and integration notes

## Tests

```bash
python -m py_compile app.py
python -m unittest discover -s tests -v
```

The v68.8 release contains 105 automated unit and product-contract tests.

## Knowledge Base and data privacy

The Creative Knowledge Base is intended to learn only from reviewed or approved patterns. Raw AI output must not update it automatically, and exact TikTok URL-to-label memory is not used for prediction.

The repository excludes API secrets, raw campaign data, exports, downloaded media and learned creator/track files through `.gitignore`. Do not commit real user data, tokens or confidential campaign patterns.

## Known limitations

- TikTok availability and platform changes can affect scraping.
- Gemini and Apify use external quotas and may incur cost.
- Some creative types are genuinely ambiguous, so human review remains part of the design.
- Streamlit session state is temporary and is not a production database.
- The detailed Drama / Creator Core mode is not included in this release.
- Knowledge Base updates remain a controlled manual process.

## Release information

Current release: **v68.8**. See [CHANGELOG.md](CHANGELOG.md) for release history and [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for the accepted product direction.

This project is intended for research, workflow automation and marketing analytics using publicly available TikTok content. It is not affiliated with TikTok, Google or Apify.
