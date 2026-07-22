# Code map

This guide shows where each responsibility lives. It is intentionally short: use it to find the right module before changing code, then rely on tests to confirm behavior.

## Main runtime path

```text
app.py
  -> final_update2_adapter.py
    -> instagram_reels_adapter.py (Instagram ingestion only)
    -> final_update2_backend.py
      -> final_update2_backend_source.py
        -> evidence_verifier.py
        -> review_routing.py
        -> drama_analysis.py (only after a drama label is confirmed)
```

## Modules

| Path | Responsibility | Change here when... |
| --- | --- | --- |
| `app.py` | Current six-step Streamlit UI, batch state, selection, review, summary and export presentation | The user-facing workflow or presentation needs to change |
| `final_update2_adapter.py` | Schema boundary between the current UI and the preserved backend | Input/output columns or shared TikTok/Instagram orchestration needs to change |
| `final_update2_backend.py` | Import-safe loader for the preserved backend functions | The backend source boundary changes; ordinary tagging changes do not belong here |
| `final_update2_backend_source.py` | Canonical scraping, Gemini prompt, guardrails, validation and tagging pipeline, followed by the preserved legacy UI | Classification behavior or the core pipeline needs to change |
| `instagram_reels_adapter.py` | Instagram URL detection, Apify calls and normalization into the shared post schema | Instagram ingestion or metric mapping needs to change |
| `evidence_verifier.py` | Conservative second opinion for ambiguous label pairs | Review-worthy label contradictions need additional evidence checks |
| `review_routing.py` | Human-review policy and deterministic QA sampling | Review escalation or audit sampling needs to change |
| `drama_analysis.py` | Conditional drama-detail and audio enrichment | A confirmed drama post needs more detailed classification |
| `model_comparison.py` | Approved Gemini model IDs and run-level model selection | Model options or defaults need to change |
| `creative_knowledge/` | Reviewed reusable creator, hashtag, market, track and keyword patterns | An approved correction should become a reusable pattern |
| `tests/` | Regression contracts for ingestion, tagging, routing, review and export | Any behavior changes or a bug is fixed |

## Current UI sections in `app.py`

1. Theme and page layout
2. Session state and runtime checkpoints
3. Display, metric and input-normalization helpers
4. Batch assembly and media preview
5. Gemini calls, Creative KB and guardrails
6. Temporal video analysis and tagging orchestration
7. Export and summary helpers
8. Six Streamlit workflow pages

## Preserved backend sections

`final_update2_backend_source.py` contains two intentionally different parts:

- **Backend (top):** Creative KB, Gemini, evidence extraction, guardrails, validation and `run_pipeline`.
- **Legacy UI (bottom):** the older Streamlit application retained for compatibility and historical reference.

The current app does not execute the legacy UI. `final_update2_backend.py` loads only the backend definitions, and `final_update2_adapter.py` translates between that backend and the current UI.

## Compatibility note

Some helper names include historical version suffixes such as `_v43` or `_v68_15`. They remain in place because tests and integration code may depend on them. Prefer a small, tested helper over renaming these functions only for style.

## Before committing a behavior change

Run:

```powershell
python -m py_compile app.py
python -m unittest discover -s tests -v
```

Never put API keys, downloaded media, raw private data or exact URL-to-label prediction memory in the repository.
