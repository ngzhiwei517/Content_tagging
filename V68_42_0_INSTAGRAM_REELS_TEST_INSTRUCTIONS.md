# Test v68.42.0 Instagram Reels integration

## First reviewed pilot

Use the supplied `UGC_v68_42_0_Instagram_Reels_Pilot_30.xlsx`. It contains 30
unique public Reel links: 15 for Katy Perry's *The One That Got Away* and 15
for Ariana Grande's *Hate That I Made You Love Me*, with high-, mid-, and
lower-view examples.

In the app:

1. Enter the Gemini API key and Apify token.
2. On **Add Posts**, choose **Instagram Reels**.
3. Upload the pilot XLSX and confirm that Current Batch shows 30 Instagram Reels and the two campaign tracks.
4. Choose **Tag every link**.
5. Keep **Gemini 3.1 Flash-Lite** as the analysis model.
6. Run tagging, inspect each Reel, and accept or correct every Review row. The reviewed rows become the first Instagram answer key.
7. Download the **Review / QA Report** and send it back to Codex.

## What to return

- the Review / QA Report XLSX;
- a short note for any clearly wrong auto-pass row;
- a screenshot only if a preview, metric, or platform label looks wrong.

Do not run either full source export yet. The first goal is to confirm live
Apify field coverage, media access, and whether suggestions make sense. The
30-row reviewed pilot can establish an initial directional result, but a
separate unseen Instagram sample is required for a formal accuracy estimate.
