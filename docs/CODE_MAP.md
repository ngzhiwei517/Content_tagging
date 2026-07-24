# Code map

This guide shows where each responsibility lives. It is intentionally short: use it to find the right module before changing code, then rely on tests to confirm behavior.

## Main runtime path

```text
app.py
  -> ugc_tagger/final_update2_adapter.py
    -> ugc_tagger/instagram_reels_adapter.py (Instagram ingestion only)
    -> ugc_tagger/final_update2_backend.py
      -> ugc_tagger/final_update2_backend_source.py
        -> ugc_tagger/evidence_verifier.py
        -> ugc_tagger/review_routing.py
        -> ugc_tagger/drama_analysis.py (only after a drama label is confirmed)
```

## Modules

| Path | Responsibility | Change here when... |
| --- | --- | --- |
| `app.py` | Current six-step Streamlit UI, batch state, selection, review, summary and export presentation | The user-facing workflow or presentation needs to change |
| `ugc_tagger/final_update2_adapter.py` | Schema boundary between the current UI and the preserved backend | Input/output columns or shared TikTok/Instagram orchestration needs to change |
| `ugc_tagger/final_update2_backend.py` | Import-safe loader for the preserved backend functions | The backend source boundary changes; ordinary tagging changes do not belong here |
| `ugc_tagger/final_update2_backend_source.py` | Canonical scraping, Gemini prompt, guardrails, validation and tagging pipeline, followed by the preserved legacy UI | Classification behavior or the core pipeline needs to change |
| `ugc_tagger/instagram_reels_adapter.py` | Instagram URL detection, Apify calls and normalization into the shared post schema | Instagram ingestion or metric mapping needs to change |
| `ugc_tagger/evidence_verifier.py` | Conservative second opinion for ambiguous label pairs | Review-worthy label contradictions need additional evidence checks |
| `ugc_tagger/review_routing.py` | Human-review policy and deterministic QA sampling | Review escalation or audit sampling needs to change |
| `ugc_tagger/drama_analysis.py` | Conditional drama-detail and audio enrichment | A confirmed drama post needs more detailed classification |
| `ugc_tagger/model_comparison.py` | Approved Gemini model IDs and run-level model selection | Model options or defaults need to change |
| `creative_knowledge/` | Reviewed reusable creator, hashtag, market, track and keyword patterns | An approved correction should become a reusable pattern |
| `tests/` | Regression contracts for ingestion, tagging, routing, review and export | Any behavior changes or a bug is fixed |

## Current UI sections in `app.py`

1. Theme and page layout
2. Session state and runtime checkpoints
3. Display, metric and input-normalization helpers
4. Batch assembly and media preview
5. Selection and the active `final_update2_adapter` call
6. Export and summary helpers
7. Six Streamlit workflow pages

`app.py` deliberately does not contain a second copy of the Gemini prompt,
Creative KB or tagging guardrails. Those responsibilities live behind
`final_update2_adapter.py`. Historical v43-v55 reference implementations were
removed from the active entry point because they were unreachable and made it
unclear which pipeline production actually used; they remain recoverable from
Git history.

## Preserved backend sections

`ugc_tagger/final_update2_backend_source.py` contains two intentionally different parts:

- **Backend (top):** Creative KB, Gemini, evidence extraction, guardrails, validation and `run_pipeline`.
- **Legacy UI (bottom):** the older Streamlit application retained for compatibility and historical reference.

The current app does not execute the legacy UI. `ugc_tagger/final_update2_backend.py` loads only the backend definitions, and `ugc_tagger/final_update2_adapter.py` translates between that backend and the current UI.

## Compatibility note

Some helper names include historical version suffixes such as `_v43` or `_v68_15`. They remain in place because tests and integration code may depend on them. Prefer a small, tested helper over renaming these functions only for style.

## Safe change boundaries

- UI copy, layout or page behavior: start in `app.py`.
- TikTok/Instagram schema mapping: start in `final_update2_adapter.py` or
  `instagram_reels_adapter.py`.
- Prompt, labels or reusable guardrails: start in
  `final_update2_backend_source.py` and add a focused regression test.
- Human-review routing: start in `review_routing.py`.
- Never place a second tagging implementation in `app.py`; call the adapter.

## Before committing a behavior change

Run:

```powershell
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests -v
```

Never put API keys, downloaded media, raw private data or exact URL-to-label prediction memory in the repository.
