# Changelog

This file keeps only the current release line. Older milestones are summarized in [docs/HISTORY.md](docs/HISTORY.md) and remain available in Git history.

## v68.42.5 — Streamlit Cloud startup hotfix

- Removed the Streamlit entry point's dependency on package-level version metadata during startup.
- Kept one canonical runtime version in the UI/backend adapter and added a regression contract for the import path.
- Changed no tagging, review, scraping, metrics or export behaviour.

## v68.42.4 — Instagram Reels finalization candidate

- Added dual-schema normalization for both nested and flat Instagram full-metrics actor payloads.
- Preserved Instagram views, shares, saves, creator, caption and audio fields across scraping, review and export.
- Marked missing Instagram Shares/Saves as `Not available` from upload through final reporting.
- Added fallback handling for per-item actor errors without changing the TikTok classifier or guardrails.
- Expanded regression coverage for real Instagram export headers and current actor output fields.

## v68.42.3 — Review-card rendering fix

- Fixed raw HTML appearing beneath Instagram metrics on the Review page.
- Kept the Instagram adapter, TikTok classifier, taxonomy and review decisions unchanged.

## v68.42.2 — Instagram Reel public metrics

- Added the Data Slayer Instagram post-details actor for public Views, Likes, Comments, Shares and Saves.
- Normalized Reel media, caption, creator and audio fields into the shared post schema.
- Retained the broad Instagram scraper as a fallback and preserved unavailable metrics as `Not available`.

## v68.42.1 — Instagram share-count candidate

- Added share-count ingestion for eligible explicit Reel URLs.
- Preserved fallback behaviour when the paid actor or share-count option is unavailable.

## v68.42.0 — Shared TikTok and Instagram workflow

- Added Instagram Reels as a platform adapter before the existing Gemini pipeline.
- Kept one taxonomy, Current Batch, review queue, summary and export flow across both platforms.
- Preserved the validated TikTok prompt and guardrail path.

## v68.41.6 — Final TikTok validation candidate

- Kept Gemini 3.1 Flash-Lite as the recommended default with no hidden 3.5 calls.
- Hardened reusable rules for quotes, humour, public-figure fanfiction, POV and subtle choreography.
- Reduced unnecessary verifier calls and retained genuinely ambiguous cases for human review.
- Preserved the v41-style workflow and detailed drama boundary.
