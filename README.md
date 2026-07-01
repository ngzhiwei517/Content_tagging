# 🎵 Content Tagging Platform

An AI-assisted Streamlit application for large-scale TikTok UGC content analysis, combining MelodyIQ filtering, Apify scraping, Google Gemini AI tagging, human review, dashboard reporting, and final dataset export.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_App-red)
![Google Gemini](https://img.shields.io/badge/Google-Gemini_AI-blue)
![Apify](https://img.shields.io/badge/Apify-TikTok_Scraper-green)

---

# 📌 Overview

This project was developed to automate TikTok User Generated Content (UGC) analysis for music marketing.

Instead of manually reviewing hundreds of TikTok posts, the platform automatically:

- Filters MelodyIQ reports
- Scrapes TikTok metadata
- Classifies content using Google Gemini AI
- Flags uncertain posts for manual review
- Generates dashboards for market-level insights
- Exports the final tagged dataset back into the original reporting format

The application significantly reduces manual effort while maintaining analyst oversight through a human-in-the-loop workflow.

---

# ✨ Features

## 📥 MelodyIQ Batch Filter

- Upload Tracklist (CSV/XLSX)
- Upload multiple MelodyIQ CSV files
- Automatic filename-to-track matching
- Country / Market filtering
- Viral date filtering (± configurable window)
- Top N post selection
- Ranking by Likes + Comments + Shares
- Country-specific KOL Size classification
- Optional TikTok Saves enrichment via Apify
- Export as CSV or Excel
- Automatic Excel tabs by market

---

## 🔎 Built-in TikTok Scraper

The application integrates directly with the **Apify TikTok Scraper**.

Features include:

- Read TikTok URLs directly from MelodyIQ output
- Automatic scraping inside the application
- Retrieve:
  - TikTok metadata
  - Cover images
  - Video URLs
  - Engagement metrics
  - Music information
  - Creator information

No manual JSON download is required.

---

# 🤖 Multi-Tier AI Tagging Pipeline

The platform uses a progressive AI workflow to maximise tagging accuracy.

## Tier 0 — Visual-only Analysis

Used when captions are missing or too vague.

Gemini analyses visual content without relying on text.

---

## Tier 1 — Cover Image + Metadata

Gemini analyses:

- Cover image
- Caption
- Hashtags
- Music metadata
- Creator metadata
- Engagement metadata

---

## Tier 2A — Video Frame Analysis

If confidence is low, the application downloads the TikTok video and samples frames for additional visual analysis.

---

## Tier 2B — Adaptive Motion Refinement

For motion-heavy content such as:

- Dance
- Lip Sync
- Cover
- Fitness

additional frames are analysed to improve movement understanding.

---

## Tier 2C — Full Video Fallback

When frame-based analysis is still uncertain, the full TikTok video is uploaded to Gemini for temporal analysis.

This improves classification for:

- Dance
- Choreography
- Lip Sync
- Performance videos
- Motion-heavy content

---

## Tier 3 — Human Review

Only uncertain posts require manual review.

This keeps automation high while maintaining quality.

---

# 🏷 AI Output

The AI automatically generates:

- Narrative
- Creative Type
- Content Details
- Confidence Score
- AI Reasoning
- Validation Status
- Human Review Flag

Supported Creative Types include:

- Dance
- Lip Sync
- Carousel
- Relationship
- Beauty
- Fashion
- POV
- Comedy
- Travel
- Gaming
- Fitness
- Celebrity Edits
- Movie / TV / Drama Edits
- Reflection
- Quotes
- Lyrics
- Lyrics Translation
- Media / Infotainment
- Cover
- Remix

---

# 📝 Human Review

The Review page allows analysts to:

- Review flagged posts
- View TikTok cover image
- Open original TikTok URL
- Edit Narrative
- Edit Creative Type
- Edit Content Details
- Use AI Suggest
- Create custom narratives
- Correct market manually
- Enter missing engagement metrics
- Remove unavailable or private posts from export

---

# 📊 Dashboard

Interactive dashboard providing:

### Executive KPIs

- Total Posts
- AI Tagged
- Automation Rate
- Average Confidence
- Total Plays
- Average Plays per Post

### Market Insights

- Market Overview
- Market Content Mix
- Engagement by Market
- Creative Type Mix
- Engagement Rate by Creative Type

### Track Insights

- Track Leaderboard
- Track Performance
- Best Performing Narratives

All charts use consistent market colour mapping across dashboards.

---

# 📤 Export

The platform supports:

- Merge AI tags back into the original MelodyIQ report
- Matching by TikTok Video ID
- URL fallback matching
- Removal of ignored posts
- CSV export
- Excel export

Optional QA columns include:

- AI Confidence
- Validation Status
- AI Tier
- Human Review Flag

---

# 🏗 Workflow

```text
Tracklist
      │
      ▼
MelodyIQ Batch Filter
      │
      ▼
Top Viral Posts
      │
      ▼
Apify TikTok Scraper
      │
      ▼
Gemini AI Tagging
      │
      ├── Tier 0  Visual-only
      ├── Tier 1  Cover + Metadata
      ├── Tier 2A Video Frames
      ├── Tier 2B Motion Refinement
      ├── Tier 2C Full Video Analysis
      └── Tier 3  Human Review
      │
      ▼
Interactive Dashboard
      │
      ▼
Export Final Dataset
```

---

# ⚙ Installation

Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/content-tagging-platform.git
cd content-tagging-platform
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run the application

```bash
streamlit run app.py
```

---

# 🔑 Required API Keys

The application requires:

- Google Gemini API Key
- Apify API Token

For production deployments, API keys should be stored using Streamlit Secrets or environment variables.

---

# 🛠 Technology Stack

- Python
- Streamlit
- Pandas
- Plotly
- OpenCV
- Google Gemini API
- Apify TikTok Scraper
- OpenPyXL
- RapidFuzz

---

# ⚠ Disclaimer

This application is intended for research, workflow automation, and marketing analytics purposes.

The platform processes publicly available TikTok content for analytical use only.

Although AI performs the majority of the tagging process, all low-confidence or ambiguous results are designed to be reviewed by a human analyst before being used in downstream reporting or decision-making.

This project is not affiliated with TikTok, Google, or Apify.


---

## ⭐ Support

If you found this project useful, consider giving the repository a ⭐.
