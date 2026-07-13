# TikTok UGC Content Tagging Platform

An AI-assisted Streamlit application for selecting, tagging, reviewing and reporting TikTok user-generated content for music marketing.

[Open the live Streamlit app](https://umgcontenttag.streamlit.app/)

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_App-red)
![Google Gemini](https://img.shields.io/badge/Google-Gemini_AI-blue)
![Apify](https://img.shields.io/badge/Apify-TikTok_Scraper-green)

## Overview

The platform reduces the manual work required to review large batches of TikTok posts while keeping human oversight for uncertain results.

It can:

- upload one or more CSV/XLSX post files or accept pasted TikTok links;
- select every link or rank the Top N posts;
- collect TikTok metadata through Apify;
- classify creative content with Gemini multimodal analysis;
- apply tagging guardrails and an optional Creative Knowledge Base;
- route uncertain posts for human review;
- summarize performance and export tagged campaign data.

## Main features

### Post selection

- Generic post files are supported as long as a TikTok link is available.
- Market and Track are optional.
- Duplicate TikTok URLs are removed automatically.
- Top posts can be ranked by Views, Total Engagement or original file order.
- Top N can be grouped by Market, Track, Source or a combined group.
- Viral-date filtering supports one shared date or a different date for each track.
- Unavailable and sensitive Top N posts are replaced by the next eligible post.

### AI tagging pipeline

Gemini analyses the cover image, caption, hashtags and post metadata first. When the result remains unclear, the app progressively checks three frames, nine frames and then the full video. A selective evidence verifier cross-checks only suspicious label conflicts; uncertain cases still go to human review.

Each post receives:

- Narrative;
- up to two Creative Types;
- Content Details;
- an internal review flag when needed.

Supported Creative Types include Dance, Lip Sync, Carousel, Relationship, Beauty, Fashion, POV, Comedy, Travel, Gaming, Fitness, Celebrity Edits, Movie/TV/Drama Edits, Reflection, Quotes, Lyrics, Lyrics Translation, Media/Infotainment, Cover, Remix and Others.

Dance is determined by visible action, not subject type. People, animals and animated subjects may be tagged Dance when clear rhythmic or choreographed movement is shown; ordinary movement or posing does not qualify.

### Human review

Flagged posts can be previewed, opened on TikTok, kept, edited or removed. Reviewers can update Narrative, Creative Type and Content Details while the system preserves the original AI result for internal auditing.

### Summary and export

The dashboard includes campaign KPIs, Creative Type performance, Market Summary, Track Summary, KOL Size performance, top posts and filtering controls.

Exports include:

- a flat marketing CSV;
- an Excel workbook with `All Posts` and market worksheets;
- an internal Review / QA workbook.

User-facing reports use **Views**, not Plays.

## Workflow

```text
Add posts
   -> Select posts
   -> Apify metadata collection
   -> Gemini multimodal tagging
   -> Guardrails and validation
   -> Human review when required
   -> Summary and export
```

The application presents this as six steps:

1. API Keys
2. Add Posts
3. Select Posts
4. Run Tagging
5. Review
6. Summary & Export

## Requirements

- Python 3.11 recommended
- Google Gemini API key
- Apify API token

API keys entered in the app are kept in Streamlit session state and are not committed to the repository.

## Run on Windows

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Alternatively, double-click `run_windows.bat`.

## Run on macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

## Technology stack

- Python, Streamlit and Pandas
- Google Gemini API
- Apify TikTok Scraper
- Plotly, OpenCV, OpenPyXL, NumPy and Pillow

## Tests

```bash
python -m py_compile app.py
python -m unittest discover -s tests -v
```

## Privacy and limitations

The repository excludes API secrets, raw campaign data, exports, downloaded media and learned creator/track files. Do not commit real tokens or confidential campaign data.

TikTok availability and platform changes can affect scraping. Gemini and Apify use external quotas, and genuinely ambiguous content may still require human review.

This project is intended for research, workflow automation and marketing analytics using publicly available TikTok content. It is not affiliated with TikTok, Google or Apify.
