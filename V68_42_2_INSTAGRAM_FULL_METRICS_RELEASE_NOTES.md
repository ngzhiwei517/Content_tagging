# v68.42.2 Instagram Reel full-metrics candidate

This candidate extends the isolated combined TikTok and Instagram Reels app.
It does not change the frozen TikTok classifier, drama logic, taxonomy, or the
public Streamlit deployment.

## Change

- Explicit Instagram `/reel/` and `/reels/` URLs use the community-maintained
  `data-slayer/instagram-post-details` Apify actor.
- The actor's nested public metrics now populate Views, Likes, Comments,
  Shares and Saves in the existing review, summary and export flow.
- Caption, hashtags, creator, thumbnail, video and audio fields from this actor
  are normalized into the same canonical post schema used by TikTok.
- Regular Instagram `/p/` and `/tv/` URLs continue through
  `apify/instagram-scraper`.
- If the full-metrics actor fails or returns no matching Reel, the app falls
  back to `apify/instagram-scraper`. Any missing Shares or Saves are shown as
  `Not available`, never as a confirmed zero.

## Validation boundary

The supplied actor output was checked locally and mapped as follows:

- Views: 2,447,124
- Likes: 108,406
- Comments: 184
- Shares: 54
- Saves: 18,217
- Audio: Ellie Goulding — Still Falling For You

This confirms schema compatibility for the supplied sample, not accuracy for
every public Instagram Reel. Compare a small pilot against the Instagram mobile
app before using the integration for reporting.

## Apify and secrets

The actor is a paid community actor billed through Apify. The app uses only the
Apify token entered for the current Streamlit session; no key or token is saved
in the repository or packaged candidate.
