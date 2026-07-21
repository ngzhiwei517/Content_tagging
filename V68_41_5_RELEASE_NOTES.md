# v68.41.5 balanced Flash-model validation candidate

## Decision

Gemini 3.1 Flash-Lite remains the recommended default. Across the completed 24-post targeted diagnostic it produced 19 semantically acceptable untouched AI results, compared with 21 for Gemini 3.5 Flash, while averaging about 15.4 seconds per post instead of 39.6 seconds and routing substantially fewer posts to review.

Gemini 3.1 Pro Preview is not included.

## Changes

- The Run Tagging page now offers only 3.1 Flash-Lite and 3.5 Flash under an optional Analysis model control.
- 3.1 is selected by default.
- When the existing targeted evidence router detects a suspicious conflict in a 3.1 result, the text-only verifier uses 3.5. Ordinary posts do not receive the extra call.
- The QA report records Verifier Model and Verifier Fallback Used.
- Clear on-screen teacher/attributed quote evidence can correct an inconsistent Fashion-only result to Quotes.
- Public-figure fanfiction versus Celebrity Edits purpose conflicts route to human adjudication.

## Honest limitations

- The 3.5 verifier sees the existing text evidence, not a fresh view of the original video.
- Subtle local humour and hand-only motion can still be missed when the visual description omits the decisive action.
- The 24-post diagnostic is targeted and cannot establish general accuracy. A separate unseen human-labelled holdout is still required.
