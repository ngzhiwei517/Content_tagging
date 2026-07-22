# Testing

## Automated checks

Run before publishing any candidate:

```bash
python -m py_compile app.py final_update2_adapter.py final_update2_backend.py final_update2_backend_source.py instagram_reels_adapter.py model_comparison.py review_routing.py
python -m unittest discover -s tests -v
```

## Manual smoke test

1. Start the Streamlit app.
2. Add a small mixed batch using an upload and pasted links.
3. Confirm both sources appear in one Current Batch without duplicates.
4. Run `Tag every link` with Gemini 3.1 Flash-Lite.
5. Confirm unavailable posts are removed and uncertain posts reach Review.
6. Keep, edit and remove one post.
7. Check Summary and download the CSV, grouped XLSX and QA report.
8. Confirm TikTok and Instagram rows remain in one export and unavailable Instagram metrics show `Not available`.

## Accuracy evaluation

Regression tests verify software behaviour; they do not establish tagging accuracy. Use a blinded, human-labelled holdout that was not used to create the current rules. Preserve untouched AI results, adjudicate disagreements, and report:

- exact primary-label agreement;
- accepted/defensible result after adjudication;
- confirmed AI-error rate;
- human-review rate;
- unavailable/removed posts;
- sample size and 95% confidence interval where appropriate.

Instagram Reels must be validated separately from the TikTok benchmark.
