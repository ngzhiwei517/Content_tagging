# Backend Architecture and Current Status

This document describes the v68.42.15 live path and the safest extension
points. The current beta keeps one General UGC tagging pipeline for TikTok and
Instagram Reels.

## Live path

1. `app.py` normalizes uploads and pasted links into one Current Batch.
2. Selection chooses Top posts or Tag every link and retrieves only ranking
   metrics that are required and still missing.
3. Direct public retrieval runs first. Paid Apify fallback must pass
   `ugc_tagger/apify_usage_guard.py` before an Actor starts.
4. `ugc_tagger/final_update2_adapter.py` groups candidates and calls the shared
   backend. Metrics-only runs skip Gemini classification.
5. `ugc_tagger/final_update2_backend.py` loads the preserved backend definitions
   without rendering its legacy UI.
6. `ugc_tagger/final_update2_backend_source.py` runs normalized evidence,
   Gemini visual analysis, reusable guardrails, temporal escalation and
   validation.
7. `ugc_tagger/evidence_verifier.py` selectively cross-checks suspicious
   label/evidence conflicts after the best temporal result is chosen.
8. `ugc_tagger/review_routing.py` decides whether unresolved evidence requires
   human review.
9. The adapter maps results into the UI/QA schema.
10. Review preserves original labels and writes final labels plus history.
11. Summary/export separates clean marketing files from internal QA
    diagnostics; optional creator enrichment remains separate from batch
    metrics.
12. Local progress checkpoints are always available. Optional
    `ugc_tagger/persistent_checkpoint.py` backends support restart or
    redeployment recovery after live configuration is verified.

## Current audit contract

- `Original AI Labels`: automated result after all automated guardrails and any targeted verifier change.
- `Final Labels`: labels used after human review.
- `Human Reviewed`: reviewer completed Keep or Remove.
- `Human Edited`: normalized final labels differ from original automated labels.
- `Label History`: ordered JSON audit events.
- `Verifier Input/Output Labels`, status, confidence, reason, evidence and triggers: internal second-pass audit fields.
- `Creative Type`: final operational alias maintained for existing Summary and exports.

## Safe future integration work

- Add persistent storage only behind a clear data-retention policy.
- Move production credentials to deployment secrets.
- Update the KB only from approved/reviewed rows.
- Keep new guardrails evidence-based and add regression tests.
- Re-run a fresh locked holdout before publishing a new accuracy claim.
- Replace the process-scoped Apify lock with a shared lease or queue before
  treating the app as a coordinated multi-replica production system.

## Do not change casually

- additive uploads and pasted links;
- unavailable/sensitive exclusion and Top-N backfill;
- two-label maximum;
- clean marketing export columns;
- original-versus-final audit history;
- the accepted five-step UI flow.
