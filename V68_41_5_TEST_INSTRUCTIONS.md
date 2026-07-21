# Test v68.41.5

## First run: targeted regression

1. Start this local candidate.
2. Add the supplied 24-post comparison workbook.
3. Select Tag every link and keep all available posts.
4. Leave Analysis model on Gemini 3.1 Flash-Lite - recommended.
5. Run tagging.
6. Complete only genuinely required review decisions; do not use AI Suggest during scoring.
7. Download the Review / QA Report and return it to Codex.

The targeted run checks known failure families. It is not an accuracy estimate.

## Second run: unseen holdout

Do not use the blank 97-row template as though it already contains a dataset. Populate it from a fresh random source pool that was not used to create these rules, keep the human labels hidden until the AI run is finished, and then adjudicate each result as Preferred, Defensible alternative, or Clear error.

Report AI-only semantic acceptance, exact preferred-label agreement, human-review rate, verifier-fallback rate, runtime and the 95% margin of error.
