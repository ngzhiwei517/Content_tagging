# v68.41.4 isolated Gemini model-comparison candidate

## Purpose

This package compares three Gemini multimodal models on the same targeted 24-post set while leaving the stable v68.41.3 candidate and live demo untouched.

Models:

- `gemini-3.1-flash-lite` — baseline
- `gemini-3.5-flash` — recommended challenger
- `gemini-3.1-pro-preview` — quota-capped diagnostic

## What changed

- Added a model selector to Run Tagging.
- Routed the initial classification, temporal fallbacks, full-video fallback and targeted verifier through the selected model.
- Recorded model ID, whether Gemini was called, comparison run ID, UTC start time and elapsed seconds in the internal QA export.
- Added model-specific QA filenames so the three reports are not overwritten.
- Cleared Review widget state before every new run so results from one model cannot appear in the next model's form.
- Paced Gemini 3.1 Pro Preview request starts below the 25 RPM limit shown in the comparison project; existing 429/503 retry handling remains active.
- Included `comparison_test_pack/UGC_v68_41_4_model_comparison_24.xlsx` with upload-ready posts, instructions, a reference key and a return checklist.

## Test rule

Run the same 24 posts once per model. Do not use AI Suggest or save human corrections. Continue directly to Summary and download the Review / QA Report; Skip is only for inspecting other flagged rows.

The 24 rows are a targeted diagnostic set, not a random accuracy sample. After choosing a model, use an unseen human-labelled holdout and report the observed accuracy with its 95% margin of error.

## Known limitation

No local test can establish live model accuracy or quota behaviour. The comparison must be run with the user's own Gemini and Apify credentials. Subtle local humour, hand-only choreography and source identity may still require conservative human review even with a stronger model.
