# Testing

## Automated checks

Run before publishing any candidate:

```bash
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests -v
```

## Manual smoke test

1. Start the Streamlit app.
2. Add a small mixed batch using an upload and pasted links. Include one
   spreadsheet whose post-link column has an unfamiliar descriptive name.
3. Confirm supported URLs are detected from values, one click adds the upload,
   and both sources appear in one Current Batch without duplicates.
4. Run `Tag every link` with Gemini 3.1 Flash-Lite.
5. Confirm unavailable posts are removed and uncertain posts reach Review.
6. Keep, edit and remove one post, preserving the original recommendation in
   QA.
7. Check Summary, fetch a small Top Creators sample and download the CSV,
   grouped XLSX and QA report.
8. Confirm creator enrichment does not overwrite batch metrics.
9. Confirm TikTok and Instagram rows remain in one export and unavailable
   Instagram metrics show `Not available`.
10. For one public Reel, confirm caption, creator, audio and video preview are
    populated after scraping.
11. If the full-metrics actor returns Shares/Saves, confirm they survive Review,
    Summary, CSV, XLSX and QA export.
12. Simulate or observe a full-metrics actor failure and confirm direct or broad
    Instagram fallback still produces a taggable row when evidence is
    available.
13. Repeat a small run in Metrics-only mode and confirm Gemini classification
    is not called.
14. Save a private Continue later link, reopen it and confirm completed work is
    not repeated. Test restart/redeployment recovery only when the optional
    remote backend is configured.
15. Use direct post URLs for the final smoke test. Confirm unsupported
    redirect/share paths follow the documented behaviour in
    [Link compatibility](LINK_COMPATIBILITY.md).

When enabled for the deployment, separately record one controlled live test of
the persistent checkpoint backend and one controlled owner-alert email. Mocked
tests do not prove either external service is configured correctly.

## Accuracy evaluation

Regression tests verify software behaviour; they do not establish tagging accuracy. Use a blinded, human-labelled holdout that was not used to create the current rules. Preserve untouched AI results, adjudicate disagreements, and report:

- exact primary-label agreement;
- accepted/defensible result after adjudication;
- confirmed AI-error rate;
- human-review rate;
- unavailable/removed posts;
- sample size and 95% confidence interval where appropriate.

Instagram Reels must be validated separately from the TikTok benchmark.
