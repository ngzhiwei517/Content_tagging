"""Instagram Reels ingestion for the shared UGC tagging pipeline.

The existing classifier consumes the record shape returned by the Clockworks
TikTok actor.  This module keeps the platform-specific Apify call isolated and
normalizes Instagram posts into that canonical shape before Gemini runs.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


TIKTOK = "TikTok"
INSTAGRAM_REELS = "Instagram Reels"
SUPPORTED_PLATFORMS = (TIKTOK, INSTAGRAM_REELS)
INSTAGRAM_REEL_ACTOR_ID = "apify/instagram-reel-scraper"
INSTAGRAM_POST_ACTOR_ID = "apify/instagram-scraper"
# Backward-compatible alias for integrations that imported the original name.
INSTAGRAM_ACTOR_ID = INSTAGRAM_REEL_ACTOR_ID


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def _number(value) -> int:
    try:
        return int(float(str(value).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _nested(record: Dict, *path, default=None):
    current = record
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
    return default if current is None else current


def _first(record: Dict, keys: Iterable[str], default=""):
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _host(url: str) -> str:
    try:
        return urlsplit(_text(url)).hostname.casefold()
    except (AttributeError, ValueError):
        return ""


def is_tiktok_post_url(url: str) -> bool:
    host = _host(url)
    return bool(host and (host == "tiktok.com" or host.endswith(".tiktok.com")))


def instagram_shortcode(url: str) -> str:
    if not is_instagram_post_url(url):
        return ""
    try:
        path = urlsplit(_text(url)).path
    except ValueError:
        return ""
    match = re.search(r"/(?:reel|reels|p|tv)/([^/?#]+)", path, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def is_instagram_post_url(url: str) -> bool:
    host = _host(url)
    if not host or not (host == "instagram.com" or host.endswith(".instagram.com")):
        return False
    try:
        path = urlsplit(_text(url)).path
    except ValueError:
        return False
    return bool(re.search(r"/(?:reel|reels|p|tv)/[^/?#]+", path, flags=re.IGNORECASE))


def is_explicit_instagram_reel_url(url: str) -> bool:
    """Return True only for URLs whose path explicitly identifies a Reel."""
    if not is_instagram_post_url(url):
        return False
    try:
        path = urlsplit(_text(url)).path
    except ValueError:
        return False
    return bool(re.search(r"/(?:reel|reels)/[^/?#]+", path, flags=re.IGNORECASE))


def detect_platform(url: str, fallback: str = "") -> str:
    if is_tiktok_post_url(url):
        return TIKTOK
    if is_instagram_post_url(url):
        return INSTAGRAM_REELS
    return fallback if fallback in SUPPORTED_PLATFORMS else ""


def is_supported_post_url(url: str) -> bool:
    return bool(detect_platform(url))


def normalize_post_url(url: str) -> str:
    """Remove tracking parameters without changing case-sensitive IG shortcodes."""
    value = _text(url)
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("?", 1)[0].rstrip("/")
    host = (parsed.hostname or "").casefold()
    if not host:
        return value.split("?", 1)[0].rstrip("/")
    port = f":{parsed.port}" if parsed.port else ""
    clean = urlunsplit(((parsed.scheme or "https").casefold(), host + port, parsed.path.rstrip("/"), "", ""))
    return clean


def post_identifier(url: str) -> str:
    platform = detect_platform(url)
    if platform == INSTAGRAM_REELS:
        code = instagram_shortcode(url)
        return f"instagram:{code}" if code else ""
    if platform == TIKTOK:
        match = re.search(r"/(?:video|photo)/(\d+)", _text(url), flags=re.IGNORECASE)
        return f"tiktok:{match.group(1)}" if match else ""
    return ""


def creator_from_url(url: str) -> str:
    value = _text(url)
    if is_tiktok_post_url(value):
        match = re.search(r"tiktok\.com/@([^/?#]+)", value, flags=re.IGNORECASE)
        return match.group(1) if match else ""
    return ""


def _instagram_record_url(record: Dict) -> str:
    return _text(_first(record, ("url", "postUrl", "inputUrl")))


def _instagram_record_shortcode(record: Dict) -> str:
    return _text(_first(record, ("shortCode", "shortcode", "code"))) or instagram_shortcode(
        _instagram_record_url(record)
    )


def _image_urls(record: Dict) -> List[str]:
    urls: List[str] = []

    def add(value):
        if isinstance(value, str) and value.strip() and value.strip() not in urls:
            urls.append(value.strip())
        elif isinstance(value, dict):
            add(_first(value, ("displayUrl", "imageUrl", "url", "thumbnailUrl")))

    for item in record.get("images", []) if isinstance(record.get("images"), list) else []:
        add(item)
    for child in record.get("childPosts", []) if isinstance(record.get("childPosts"), list) else []:
        add(child)
    add(record.get("displayUrl"))
    add(record.get("thumbnailUrl"))
    return urls


def _video_url(record: Dict) -> str:
    value = _first(record, ("videoUrl", "videoURL", "video_url", "downloadUrl"))
    if isinstance(value, list):
        return _text(value[0]) if value else ""
    return _text(value)


def _music(record: Dict) -> Dict:
    info = record.get("musicInfo") if isinstance(record.get("musicInfo"), dict) else {}
    meta = record.get("metaData") if isinstance(record.get("metaData"), dict) else {}
    name = _text(
        _first(info, ("song_name", "songName", "musicName", "audio_name", "title"))
        or _first(record, ("audioName", "musicName", "soundName"))
        or _first(meta, ("song_name", "musicName", "audioName"))
    )
    artist = _text(
        _first(info, ("artist_name", "artistName", "musicAuthor", "author"))
        or _first(record, ("musicAuthor", "audioAuthor"))
        or _first(meta, ("artist_name", "musicAuthor"))
    )
    return {"musicName": name, "musicAuthor": artist}


def normalize_instagram_record(record: Dict, requested_url: str = "") -> Dict:
    """Return one Instagram item in the classifier's canonical record shape."""
    raw = dict(record or {})
    requested_url = _text(requested_url)
    public_url = _instagram_record_url(raw) or requested_url
    code = _instagram_record_shortcode(raw) or instagram_shortcode(requested_url)
    images = _image_urls(raw)
    video_url = _video_url(raw)
    type_text = _text(raw.get("type")).casefold()
    product_type = _text(raw.get("productType")).casefold()
    children = raw.get("childPosts") if isinstance(raw.get("childPosts"), list) else []
    is_slideshow = (
        type_text in {"sidecar", "carousel", "carousel_container"}
        or product_type in {"carousel", "carousel_container"}
        or len(children) >= 2
        or (not video_url and len(images) >= 2)
    )
    creator = _text(_first(raw, ("ownerUsername", "username")))
    creator_display = _text(_first(raw, ("ownerFullName", "fullName")))
    followers = _number(
        _first(raw, ("ownerFollowersCount", "followersCount", "followerCount"))
        or _nested(raw, "owner", "followersCount", default=0)
    )
    hashtags = raw.get("hashtags") if isinstance(raw.get("hashtags"), list) else []
    if not hashtags:
        hashtags = re.findall(r"#([^\s#]+)", _text(_first(raw, ("caption", "text"))))
    cover = _text(_first(raw, ("displayUrl", "thumbnailUrl"))) or (images[0] if images else "")
    duration = _number(_first(raw, ("videoDuration", "duration")))
    music = _music(raw)

    normalized = {
        "id": _text(_first(raw, ("id", "postId", "pk"))) or code or normalize_post_url(public_url),
        "url": public_url,
        "webVideoUrl": public_url,
        "submittedVideoUrl": requested_url or public_url,
        "inputUrl": requested_url or _text(raw.get("inputUrl")) or public_url,
        "text": _text(_first(raw, ("caption", "text"))),
        "hashtags": hashtags,
        "playCount": _number(
            _first(raw, ("videoPlayCount", "videoViewCount", "viewCount", "playsCount"))
        ),
        "diggCount": _number(_first(raw, ("likesCount", "likeCount", "likes"))),
        "commentCount": _number(_first(raw, ("commentsCount", "commentCount", "comments"))),
        "shareCount": _number(_first(raw, ("sharesCount", "shareCount", "shares"))),
        "collectCount": _number(_first(raw, ("savesCount", "saveCount", "saves"))),
        "authorMeta": {
            "name": creator,
            "nickName": creator_display,
            "fans": followers,
            "followers": followers,
        },
        "musicMeta": music,
        "videoMeta": {
            "originalCoverUrl": cover,
            "coverUrl": cover,
            "downloadAddr": video_url,
            "duration": duration,
            "webVideoUrl": public_url,
        },
        "mediaUrls": [video_url] if video_url else [],
        "images": images,
        "slideshowImageLinks": images if is_slideshow else [],
        "isSlideshow": bool(is_slideshow),
        "createTimeISO": _text(_first(raw, ("timestamp", "takenAt", "createdAt"))),
        "locationCreated": "",
        "_platform": INSTAGRAM_REELS,
        "platform": INSTAGRAM_REELS,
        "instagramShortcode": code,
        "instagramProductType": _text(raw.get("productType")),
        "instagramType": _text(raw.get("type")),
        "instagramMetricsUnavailable": [
            name
            for name, keys in {
                "Shares": ("sharesCount", "shareCount", "shares"),
                "Saves": ("savesCount", "saveCount", "saves"),
            }.items()
            if not any(key in raw and raw.get(key) is not None for key in keys)
        ],
    }
    if _text(raw.get("error")) or _text(raw.get("errorCode")):
        normalized["error"] = _text(raw.get("error"))
        normalized["errorCode"] = _text(raw.get("errorCode"))
    return normalized


def _dataset_id(run) -> str:
    if isinstance(run, dict):
        return _text(run.get("defaultDatasetId") or run.get("default_dataset_id"))
    return _text(getattr(run, "default_dataset_id", None) or getattr(run, "defaultDatasetId", None))


def _run_actor_items(client, actor_id: str, run_input: Dict) -> List[Dict]:
    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = _dataset_id(run)
    if not dataset_id:
        raise RuntimeError("Instagram Apify run finished but no default dataset was returned.")
    return [item for item in client.dataset(dataset_id).iterate_items() if isinstance(item, dict)]


def scrape_instagram_posts(
    links: List[str],
    apify_token: str,
    *,
    client=None,
) -> List[Dict]:
    """Scrape direct Instagram post/Reel URLs and return canonical records.

    ``client`` is injectable for deterministic tests. The runtime creates an
    ``ApifyClient`` only after the user supplies a token in the session.
    """
    requested: List[str] = []
    seen = set()
    for link in links or []:
        if not is_instagram_post_url(link):
            continue
        key = post_identifier(link) or normalize_post_url(link)
        if key and key not in seen:
            seen.add(key)
            requested.append(_text(link))
    if not requested:
        return []
    if not _text(apify_token) and client is None:
        raise RuntimeError("Missing Apify token.")
    if client is None:
        try:
            from apify_client import ApifyClient
        except Exception as exc:  # pragma: no cover - dependency error is runtime-only
            raise RuntimeError("Missing dependency: install with `pip install apify-client`.") from exc
        client = ApifyClient(apify_token)

    reel_links = [link for link in requested if is_explicit_instagram_reel_url(link)]
    generic_links = [link for link in requested if link not in reel_links]
    raw_items: List[Dict] = []

    # Apify's dedicated Reel actor exposes sharesCount when this paid option is
    # enabled. It also returns the metadata and media used by the shared Gemini
    # pipeline, so explicit Reel URLs do not need a second scrape.
    if reel_links:
        try:
            reel_items = _run_actor_items(
                client,
                INSTAGRAM_REEL_ACTOR_ID,
                {
                    "username": reel_links,
                    "resultsLimit": len(reel_links),
                    "includeSharesCount": True,
                    "includeTranscript": False,
                    "includeDownloadedVideo": False,
                },
            )
        except Exception:
            # Keep tagging usable when the account does not have access to the
            # paid share-count option. The normal missing-metric handling will
            # then report Shares as unavailable instead of a false zero.
            reel_items = []
        raw_items.extend(reel_items)

        returned_codes = {
            _instagram_record_shortcode(item)
            for item in reel_items
            if _instagram_record_shortcode(item)
        }
        generic_links.extend(
            link for link in reel_links if instagram_shortcode(link) not in returned_codes
        )

    # Regular Instagram posts/carousels and Reel fallbacks continue through the
    # existing broad actor so a share-count entitlement issue never blocks the
    # rest of the tagging workflow.
    if generic_links:
        raw_items.extend(
            _run_actor_items(
                client,
                INSTAGRAM_POST_ACTOR_ID,
                {
                    "directUrls": generic_links,
                    "resultsType": "posts",
                    "resultsLimit": len(generic_links),
                    "addParentData": True,
                },
            )
        )

    by_code: Dict[str, Dict] = {}
    by_url: Dict[str, Dict] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = _instagram_record_shortcode(item)
        if code:
            by_code[code] = item
        url = _instagram_record_url(item)
        if url:
            by_url[normalize_post_url(url)] = item

    records: List[Dict] = []
    for link in requested:
        code = instagram_shortcode(link)
        item = by_code.get(code) if code else None
        if not isinstance(item, dict):
            item = by_url.get(normalize_post_url(link))
        if isinstance(item, dict):
            records.append(normalize_instagram_record(item, link))
        else:
            records.append({
                "id": code or normalize_post_url(link),
                "url": link,
                "webVideoUrl": link,
                "submittedVideoUrl": link,
                "inputUrl": link,
                "_platform": INSTAGRAM_REELS,
                "platform": INSTAGRAM_REELS,
                "error": "POST_NOT_FOUND",
                "errorCode": "POST_NOT_FOUND",
            })
    return records


def platform_for_record(record: Optional[Dict], fallback_url: str = "") -> str:
    record = record or {}
    explicit = _text(record.get("_platform") or record.get("platform"))
    if explicit in SUPPORTED_PLATFORMS:
        return explicit
    return detect_platform(
        _text(_first(record, ("webVideoUrl", "submittedVideoUrl", "url", "inputUrl")))
        or fallback_url,
        TIKTOK,
    )
