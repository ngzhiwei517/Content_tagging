# v68.42.0 Instagram Reels integration candidate

## What is included

- One combined TikTok + Instagram Reels application and Current Batch.
- A platform selector on Add Posts; no separate Instagram product or taxonomy.
- CSV/XLSX upload and pasted-link support for direct Instagram `/reel/`, `/p/`, `/tv/`, and `/reels/` post URLs.
- A separate `apify/instagram-scraper` ingestion adapter that normalizes Instagram output before the shared Gemini pipeline.
- The same General UGC creative types, guardrails, review actions, summary, CSV, grouped XLSX, and QA workbook used by TikTok.
- A `Platform` field across Current Batch, Review, Summary, Final Output, Links Only, and QA exports.
- A `Metrics Unavailable` field when Instagram does not expose shares or saves.

## TikTok regression boundary

- The current TikTok prompt wording and v68.41.6 classification guardrails remain unchanged.
- Drama logic was not changed.
- Instagram receives platform-specific prompt context only after normalization.

## Validation status

- Local normalization, routing, UI, and export tests pass.
- The Instagram Apify call requires a user token and has not been live-run from this repository.
- TikTok's previous accuracy estimate does **not** apply to Instagram Reels. A separate reviewed Reels sample is required before release.

## Known limitations

- Instagram may omit shares, saves, or follower count for a direct post.
- Private, deleted, login-restricted, or unavailable posts are auto-removed using the same workflow rule as TikTok.
- CDN media URLs are temporary and are used only during the current tagging run.
- Instagram carousel analysis currently follows the existing shared cover-first pipeline; multi-image accuracy needs separate validation.
