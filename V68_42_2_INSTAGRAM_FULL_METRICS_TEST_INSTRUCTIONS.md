# Test Instagram Reel full metrics

Use the existing 30-row Instagram pilot workbook. Start with only three Reels
to limit Apify and Gemini usage.

1. Extract the candidate ZIP.
2. Start the app with `RUN_MAC.command` on macOS or `RUN_WINDOWS.bat` on Windows.
3. Enter the Gemini API key and Apify token for this session.
4. Add `UGC_v68_42_0_Instagram_Reels_Pilot_30.xlsx`.
5. Choose Instagram Reels and set Top posts to 3.
6. Run tagging, then open Review and Summary.
7. Confirm Views, Likes, Comments, Shares and Saves are populated when the
   actor returned them.
8. Compare the three Shares and Saves values with the Instagram mobile app.
9. Check that up to two Creative Types can still be selected during review.
10. Download the Review / QA Report and send it back for verification.

Expected behavior:

- A returned zero is displayed as `0`.
- A metric absent from the actor output is displayed as `Not available`.
- TikTok posts continue through the frozen TikTok path.
- TikTok and Instagram rows remain in one review queue and combined export.

If the Data Slayer actor fails, the app automatically tries the broad Instagram
scraper. The batch remains usable, but Shares or Saves may then show as
`Not available`.
