# Test Instagram Reel shares

Use the existing 30-row Instagram pilot workbook. To limit Apify and Gemini
usage, test three rows first.

1. Start the candidate app and enter the Gemini key and Apify token.
2. Add `UGC_v68_42_0_Instagram_Reels_Pilot_30.xlsx`.
3. Choose Instagram Reels and set Top posts to 3.
4. Run tagging and continue to Review or Summary.
5. Confirm that Shares contains a number for public Reels. A genuine zero is
   valid; `Not available` means Apify did not return the metric.
6. Confirm Saves remains `Not available` unless supplied by the source file.
7. Download the Review / QA Report and send it back for verification.

If all three rows show Shares as `Not available`, confirm that the Apify plan
supports the paid `includeSharesCount` option before running a larger batch.

