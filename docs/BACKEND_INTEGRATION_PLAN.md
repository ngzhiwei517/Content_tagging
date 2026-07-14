# Backend Architecture and Current Status

The original phased integration remains complete in v68.15. This document describes the live path and the safest extension points. The v68.15 demo does not change the General UGC tagging backend.

## Live path

1. `app.py` normalizes uploads and pasted links into one Current Batch.
2. Selection chooses Top posts or Tag every link.
3. `final_update2_adapter.py` groups candidates and calls the backend.
4. `final_update2_backend.py` loads the preserved backend definitions without rendering its legacy UI.
5. `final_update2_backend_source.py` runs Apify normalization, Gemini visual analysis, reusable guardrails, temporal escalation and validation.
6. `evidence_verifier.py` selectively cross-checks suspicious label/evidence conflicts after the best temporal result is chosen.
7. `review_routing.py` decides whether unresolved evidence requires human review.
8. The adapter maps results into the UI/QA schema.
9. Review preserves original labels and writes final labels plus history.
10. Summary/export separates clean marketing files from internal QA diagnostics.

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

## Do not change casually

- additive uploads and pasted links;
- unavailable/sensitive exclusion and Top-N backfill;
- two-label maximum;
- clean marketing export columns;
- original-versus-final audit history;
- the accepted six-step UI flow.
