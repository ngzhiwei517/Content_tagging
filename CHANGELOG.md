# Changelog

This file keeps only the current release line. Older milestones are summarized in [docs/HISTORY.md](docs/HISTORY.md) and remain available in Git history.

## Unreleased — Readability-only cleanup

- Removed the unreachable v43-v55 reference tagging backend from `app.py`.
- Clarified that the active Streamlit app delegates classification through
  `ugc_tagger/final_update2_adapter.py`.
- Updated the code map with safe change boundaries for future maintainers.
- Changed no prompts, guardrails, confidence thresholds, review policy, UI
  behavior or export schema.

## v68.42.9 — Optional missing-metrics completion

- Added a collapsed Review section only when one or more engagement metrics are unavailable.
- Allowed reviewers to enter any verified values while leaving the remaining fields blank as `Not available`.
- Recorded manually completed metric names, source and UTC capture time in the internal QA export.
- Kept tagging, confidence routing and automatic removal behaviour unchanged.

## v68.42.8 — Manual review for restricted posts

- Removed the misleading `Others` AI suggestion when TikTok blocks automated media and metadata access.
- Kept viewable restricted posts in Human Review with blank fields for manual tagging.
- Allowed unavailable metrics to remain blank while the UI displays `Not available`.
- Kept deleted, private and unopenable posts on the existing automatic removal path.

## v68.42.7 — Automatic platform detection

- Replaced the TikTok / Instagram input selector with one mixed post input.
- Detected each uploaded or pasted link as TikTok or Instagram automatically.
- Kept mixed-platform posts in the same Current Batch, review queue, summary and exports.

## v68.42.6 — Entertainment News review routing

- Routed high-confidence Movie/Tv/Drama Edits results to Human Review when the AI's own visual analysis explicitly identifies Entertainment News or real-person reporting evidence.
- Kept the predicted broad label unchanged so a reviewer confirms the post's purpose instead of relying on an automatic relabel.
- Added controls for genuine fictional drama edits to avoid routing ordinary scene montages as entertainment reporting.

## v68.42.5 — Streamlit Cloud startup hotfix

- Removed the Streamlit entry point's dependency on package-level version metadata during startup.
- Kept one canonical runtime version in the UI/backend adapter and added a regression contract for the import path.
- Documented the verified TikTok and Instagram post-link compatibility boundary from the 23-case deployed-app smoke test.
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
