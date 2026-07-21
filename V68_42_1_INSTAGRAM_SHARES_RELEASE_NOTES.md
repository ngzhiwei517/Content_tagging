# v68.42.1 Instagram Reel shares candidate

This candidate extends the isolated v68.42.0 TikTok and Instagram Reels app.
It does not change the frozen TikTok classifier, drama logic, or the public
Streamlit deployment.

## Change

- Explicit `/reel/` and `/reels/` URLs use Apify's maintained
  `apify/instagram-reel-scraper` actor.
- The actor request enables `includeSharesCount` so returned `sharesCount`
  values populate Shares, Total Engagement, Engagement Rate and Shares Rate.
- Transcript and downloaded-video add-ons stay disabled.
- Regular `/p/` and `/tv/` URLs continue through `apify/instagram-scraper` so
  posts and carousels retain their existing support.
- If the paid share-count actor is unavailable for the user's Apify account,
  the app falls back to the broad Instagram actor and reports Shares as
  `Not available` rather than zero.
- Saves remain `Not available` for public third-party Reels unless the source
  file already contains a genuine Saves metric.

## Apify requirement

The `includeSharesCount` option is available only to eligible paid Apify
accounts. The app uses the Apify token entered for the current Streamlit
session and does not store it in the repository or exported checkpoint.

