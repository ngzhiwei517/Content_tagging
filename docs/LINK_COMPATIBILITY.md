# Link Compatibility

## Recommended input

Use a direct public post URL whenever possible:

- TikTok video: `https://www.tiktok.com/@creator/video/POST_ID`
- TikTok photo/carousel: `https://www.tiktok.com/@creator/photo/POST_ID`
- Instagram Reel: `https://www.instagram.com/reel/SHORTCODE/`
- Instagram post/carousel: `https://www.instagram.com/p/SHORTCODE/`

The app accepts these links from CSV/XLSX uploads or pasted input. Market and Track remain optional.

## Verified compatibility

The deployed app was checked with 23 URL-format cases on 23 July 2026. Eighteen cases passed, five were recorded as known compatibility limitations, and no test outcome was left blank.

### TikTok

| Link type | Result | Notes |
|---|---|---|
| Full `/@creator/video/POST_ID` URL | Supported | Recommended format |
| Full `/@creator/photo/POST_ID` URL | Supported | Photo/carousel posts enter the shared workflow |
| Full URL with tracking parameters | Supported | Tracking parameters are normalized |
| Full URL without `www` | Supported | Detected and scraped |
| Full URL using `http` | Supported | Redirected successfully; `https` remains recommended |
| `vt.tiktok.com` short link | Known limitation | May return `POST_NOT_FOUND` in Streamlit Cloud |
| `vm.tiktok.com` short link | Known limitation | May return `POST_NOT_FOUND` in Streamlit Cloud |
| `tiktok.com/t/...` share link | Known limitation | Did not resolve reliably in the deployed app |
| Legacy `m.tiktok.com/v/...` link | Known limitation | Did not resolve reliably in the deployed app |

For an unsupported redirect/share link, open it in a browser and copy the final direct `/@creator/video/POST_ID` or `/photo/POST_ID` URL.

### Instagram

| Link type | Result | Notes |
|---|---|---|
| Standard `/reel/SHORTCODE/` URL | Supported | Recommended Reel format |
| Plural `/reels/SHORTCODE/` URL | Supported | Entered the shared workflow |
| `/p/SHORTCODE/` post or carousel | Supported | Entered the shared workflow |
| Legacy `/tv/SHORTCODE/` video | Supported | Added and scraped in the deployed test |
| Direct link without `www` | Supported | Detected and scraped |
| Reel URL with tracking parameters | Supported | Tracking parameters are ignored |
| `/share/reel/SHORTCODE/` path | Known limitation | Use the final direct `/reel/SHORTCODE/` URL |

## Expected rejection

The following are not individual supported posts and were correctly rejected or excluded:

- TikTok creator profiles, Live pages and hashtag pages;
- Instagram creator profiles, Stories and Explore pages;
- links without an `http://` or `https://` scheme.

## Scope of this result

This is an input-compatibility smoke test, not a tagging-accuracy benchmark. A supported URL can still be unavailable, private, deleted, sensitive or blocked by a platform/scraper response. Those posts follow the app's normal removal behaviour.
