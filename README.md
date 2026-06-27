# 🎵 AI UGC Content Tagging Platform

An AI-assisted Streamlit application for automating TikTok User Generated Content (UGC) analysis and tagging.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_App-red)
![Gemini](https://img.shields.io/badge/Google-Gemini_AI-blue)
![Apify](https://img.shields.io/badge/Apify-TikTok_Scraper-green)

---

## 📌 Overview

This project automates the manual workflow of tagging TikTok UGC posts for music marketing analysis.

Instead of manually reviewing every TikTok post, the application uses Google's Gemini AI to generate structured content tags while allowing analysts to review uncertain cases before exporting the final dataset.

---

## ✨ Features

### 📥 Data Input

- Upload MelodyIQ CSV/XLSX reports

---

### 🤖 AI Tagging Pipeline

The application uses a multi-stage AI workflow.

#### Tier 0
Visual-only analysis for posts with missing or weak captions.

#### Tier 1
Cover image + metadata analysis.

#### Tier 2
Video frame analysis when confidence is low.

#### Tier 3
Human review for uncertain or incomplete posts.

---

### 📝 Human Review

Supports:

- Narrative editing
- Creative Type editing
- Content Details editing
- AI Suggest
- Custom Narrative
- Manual market correction
- Manual engagement metrics
- Remove unavailable/private posts from export

---

### 📊 Dashboard

Interactive dashboard showing:

- Total posts
- Automation rate
- AI confidence
- Review status
- Market overview
- Narrative distribution
- Creative type distribution
- Track leaderboard

---

### 📤 Export

- Merge AI results back into the original spreadsheet
- Match using TikTok Video ID
- Export CSV
- Export Excel (.xlsx)

---

# 🏗 Workflow

TikTok Viral Radar
        │
Select Country + Track
        │
        ▼
MelodyIQ / TikTok Source
        │
        ▼
Apify TikTok Scraper
        │
        ▼
Gemini AI Tagging

Tier 0
   │
Tier 1
   │
Tier 2
   │
Tier 3 (Human Review)

        │
        ▼
Export Final Dataset
---

# ⚙ Installation

Clone the repository

git clone https://github.com/YOUR_USERNAME/Content_tagging.git
cd Content_tagging
Install dependencies

pip install -r requirements.txt
Run locally

streamlit run app.py

---

# 🔑 Required API Keys

- Google Gemini API Key
- Apify API Token

For production deployments, API keys should be stored using Streamlit Secrets or environment variables.

---

# ⚠ Disclaimer

This project is intended for research and workflow automation purposes.

All TikTok content processed by the application is publicly available content.

AI-generated tags should be reviewed by a human before being used in downstream reporting.

---

# 👨‍💻 Author

Developed as an AI workflow automation project for large-scale TikTok UGC content analysis.

---

## ⭐ If you find this project useful, consider giving it a star.
