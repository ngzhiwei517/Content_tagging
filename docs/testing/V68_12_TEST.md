# v68.12 Targeted Verifier Test

This is a development regression test, not a new accuracy claim.

The verifier re-checks the existing Narrative and Content Details. It does not inspect a new set of frames, so a fresh locked holdout is still required for final accuracy reporting.

## Run

1. Upload `v68_10_final_blind_reserve_20_posts.xlsx`.
2. Choose **Tag every link**.
3. Do not enable Top N or a date window.
4. Start tagging and complete any flagged reviews normally.
5. Download **Review / QA Report** and send that workbook for comparison.

## Check

The internal QA workbook now includes:

- `Verifier Status`
- `Verifier Input Labels`
- `Verifier Output Labels`
- `Verifier Confidence`
- `Verifier Reason`
- `Verifier Evidence`
- `Verifier Triggers`

Expected behaviour:

- most clear posts remain `not_run`;
- suspicious conflicts may be `confirmed`, `changed` or `review`;
- an automatic change requires explicit evidence and at least 86% verifier confidence;
- a label cannot be removed without a direct contradiction;
- uncertain results keep their labels and go to human review;
- optional verifier API failures leave the existing result unchanged.

If this 20-post regression has no clear regression, run one fresh unseen 100-post holdout before reporting a new accuracy figure.
