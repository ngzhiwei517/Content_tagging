# AGENTS.md — UGC Content Tagging Tool

## Project summary
This repository contains a Streamlit prototype for AI-assisted TikTok and Instagram Reels UGC creative-type tagging in music marketing workflows. The tool accepts generic post CSV/XLSX files or pasted post links, scrapes platform metadata using Apify, classifies posts using Gemini, applies guardrails and a Creative Knowledge Base, supports human review, and exports clean marketing reports.

v68.42.5 is the current Instagram Reels finalization candidate. It preserves the validated v68.41.6 TikTok path and runs TikTok and Instagram Reels through one shared workflow.

## Current product direction
- Use the v68.14 implementation and its v41-style UI flow as the baseline unless the user explicitly says otherwise.
- The app is now general UGC tagging by default. Do not show a General vs Drama selector in the current UI.
- Drama / Creator Core detailed mode is a possible future route, but do not integrate it unless explicitly requested.
- User-facing wording should say Post, TikTok post, Instagram Reel, or UGC post. Avoid MelodyIQ-specific wording unless working on legacy compatibility.
- Marketing users are the target users, not analysts. Keep pages clean, direct, and non-technical.

## Main workflow
1. Setup / API Keys
2. Add Posts
   - Upload one or more CSV/XLSX post files
   - Optionally paste TikTok or Instagram post links
   - Both uploaded rows and pasted links add into one Current Batch
3. Select Posts
   - Top posts
   - Tag every link
   - Optional grouping/filtering only when needed
4. Run Tagging
5. Review
6. Summary & Export

## Core tagging pipeline
Input posts -> Apify scraping -> Gemini multimodal analysis -> global/semantic guardrails -> optional Creative Knowledge Base -> market guardrails -> temporal validation -> targeted evidence verification for suspicious conflicts -> human review if needed -> export.

## Important behavior rules
- The only required input is a supported TikTok or Instagram post link column or pasted links.
- Market is optional. If missing, keep blank in the working data and group/export as Other only when needed.
- Track is optional. If missing, show Not specified in summaries instead of blank.
- CSV and pasted links are additive. Adding one source must never erase the other.
- Multiple CSV/XLSX files must be supported.
- Duplicate post URLs should be deduplicated by TikTok video ID, Instagram shortcode, or normalized URL.
- Deleted/private/unavailable posts should be auto-removed, not sent to manual review.
- Blank AI tag should become Others rather than empty output.
- Do not expose technical tier/confidence/guardrail details in marketing-facing Summary. Keep those only in QA/report exports.
- Preserve Original AI Labels separately from Final Labels. Human review must never overwrite the automated recommendation.
- Record Human Reviewed, Human Edited, and ordered Label History fields in internal QA.
- Record verifier status, input/output labels, confidence, evidence and triggers in internal QA when the targeted verifier runs.
- Creative Type remains the operational alias of Final Labels for Summary/export compatibility.
- Speech, dialogue subtitles, and personal reflection are not Lyrics without explicit song-lyric evidence.
- Secondary Dance requires explicit choreography or coordinated dance evidence.
- Dance is action-based rather than species-based: people, animals, or animated subjects may be Dance when explicit rhythmic or choreographed movement is visible. Ordinary animal movement, posing, or rolling is not Dance.
- Preserve the shared date-window default and the optional per-track date mode.
- Apply each enabled track's inclusive ±N-day window before Top N ranking and backfill candidate selection.

## Export rules
- Final CSV: one flat table, sorted/grouped by Market if available.
- Final XLSX: All Posts plus one sheet per market if market exists. Source remains a column, not separate source tabs.
- Review / QA Report: internal file only; includes Original AI Labels, Final Labels, Human Reviewed, Human Edited, Label History, confidence, tier, validation and review reason.
- Include metrics when available: Views, Likes, Comments, Shares, Saves, Followers, KOL Size, Engagements, Engagement Rate, Likes Rate, Comments Rate, Shares Rate, Saves Rate.
- Use Views, not Plays, in user-facing UI/export labels.

## UI rules
- Keep the v68.14 UI and v41-style flow unless told otherwise.
- Prefer clean, mature, marketing-friendly UI.
- Avoid too many emojis, playful icons, or overly textbook/corporate styling.
- Avoid long explanations in the UI. Use short labels and short helper text only when necessary.
- If upload detection succeeds, do not show a large column-mapping section. Hide fixes under an advanced/optional area only when needed.
- Current Batch should be the main preview after adding uploaded rows or pasted links.
- Review page should be simple and close to the original app style: preview/link, creator/market/track/caption/metrics, suggested tag, edit fields, Keep/Edit/Remove actions.
- Summary should focus on marketing value: KPIs, Creative Type Mix, Views by Creative Type, Market Summary, Track Summary, Top Posts, Downloads.

## Knowledge Base policy
- Do not learn from every raw AI output automatically.
- Future database/KB updates should come only from reviewed or approved rows.
- The KB should store reusable patterns such as creator, track, market, post format, keywords, hashtags, and corrected labels.
- Do not use exact post URL -> label memory for prediction.

## Safety and secrets
- Never hardcode API keys, Apify tokens, Gemini keys, or credentials.
- Never commit real user data, API keys, downloaded media, or large Apify datasets.
- Add placeholders or environment variables for secrets.
- If unsure whether data is sensitive, ask before saving it into the repo.

## Coding conventions
- Keep code modular where possible: input handling, selection, scraping, tagging, review, summary, export.
- Preserve existing working behavior unless the task explicitly requests a change.
- Prefer small, reviewable patches over large rewrites.
- Add clear helper functions instead of duplicating logic.
- Use pandas safely: handle missing columns, NaN, duplicate column names, and mixed CSV/XLSX structures.
- Keep UI text concise and consistent.

## Testing expectations
Before returning work, run at minimum:
- python -m py_compile app.py
- python -m unittest discover -s tests -v
- Any lightweight import or Streamlit smoke check that is safe in the current environment
- For UI-only changes, run a syntax check and describe manual Streamlit test steps

## Definition of done
A task is done only when:
- The app still starts without syntax errors.
- The requested UI/backend behavior is implemented.
- Existing core flows are not broken.
- Any known limitations are clearly stated.
- No secrets or private data are introduced.
