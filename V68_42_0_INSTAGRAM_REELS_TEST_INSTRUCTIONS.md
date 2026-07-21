# Test v68.42.0 Instagram Reels integration

## First live smoke test

Use **5 public Instagram Reels** that you can open without logging in:

1. one clear Dance post;
2. one clear Lip Sync or Beauty post;
3. one text-led Quotes, POV, or Reflection post;
4. one Comedy or Slice of Life post;
5. one difficult/ambiguous post.

In the app:

1. Enter the Gemini API key and Apify token.
2. On **Add Posts**, choose **Instagram Reels**.
3. Paste the five Reel links and add them to the Current Batch.
4. Choose **Tag every link**.
5. Keep **Gemini 3.1 Flash-Lite** as the analysis model.
6. Run tagging, check every Review row, and complete the review normally.
7. Download the **Review / QA Report** and send it back to Codex.

## What to return

- the Review / QA Report XLSX;
- a short note for any clearly wrong auto-pass row;
- a screenshot only if a preview, metric, or platform label looks wrong.

Do not run a large Instagram batch yet. The first goal is to confirm live Apify field coverage and media access, not to estimate accuracy.
