# UI Specification — v68.42.15

## Design tone

Clean, mature, marketing-friendly and direct. Preserve the accepted v41-style flow and the current v66.6 visual design.

## Pages

1. Add Posts
2. Select Posts
3. Run Tagging
4. Review
5. Summary & Export

Gemini and Apify credentials are deployment-managed. Do not show a credential
entry page to marketing users.

## Product rules

- General UGC is assumed; no General/Drama selector.
- Current Batch is the main upload/pasted-link preview.
- Optional grouping and filters remain compact.
- Date filtering defaults to one shared date; mixed-track batches may choose separate editable dates per track.
- Review shows only information needed to decide Keep, Edit or Remove.
- Summary shows marketing insights, not AI debug fields.
- Summary keeps marketing KPIs, creative performance, market and track views,
  Top Creators, Top Posts, Taggy assistance and downloads concise.
- Do not add a Source Summary or duplicate dashboard-wide tables unless the
  user explicitly requests them.
- QA diagnostics and label history appear only in the internal QA download.

## Downloads

- Final CSV
- Grouped XLSX
- Review / QA Report
