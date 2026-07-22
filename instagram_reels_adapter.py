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
INSTAGRAM_REEL_ACTOR_ID = "data-slayer/instagram-post-details"
INSTAGRAM_POST_ACTOR_ID = "apify/instagram-scraper"
# Backward-compatible alias for integrations that imported the original name.
INSTAGRAM_ACTOR_ID = INSTAGRAM_REEL_ACTOR_ID


# -----------------------------------------------------------------------------
# Platform URL identity and normalization
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# Instagram payload extraction and canonical record mapping
# -----------------------------------------------------------------------------


def _instagram_record_url(record: Dict) -> str:
    return _text(
        _first(record, ("url", "postUrl", "post_url", "permalink", "inputUrl"))
    )


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
            add(
                _first(
                    value,
                    ("displayUrl", "imageUrl", "url", "thumbnailUrl", "thumbnail_url"),
                )
            )

    for item in record.get("images", []) if isinstance(record.get("images"), list) else []:
        add(item)
    for child in record.get("childPosts", []) if isinstance(record.get("childPosts"), list) else []:
        add(child)
    image_versions = record.get("image_versions")
    if isinstance(image_versions, dict):
        for item in image_versions.get("items", []) if isinstance(image_versions.get("items"), list) else []:
            add(item)
    add(record.get("displayUrl"))
    add(record.get("thumbnailUrl"))
    add(record.get("thumbnail_url"))
    return urls


def _video_url(record: Dict) -> str:
    value = _first(
        record,
        ("videoUrl", "videoURL", "video_url", "media_url", "downloadUrl"),
    )
    if isinstance(value, list):
        return _text(value[0]) if value else ""
    return _text(value)


def _music(record: Dict) -> Dict:
    info = record.get("musicInfo") if isinstance(record.get("musicInfo"), dict) else {}
    meta = record.get("metaData") if isinstance(record.get("metaData"), dict) else {}
    clips = record.get("clips_metadata") if isinstance(record.get("clips_metadata"), dict) else {}
    original_sound = (
        clips.get("original_sound_info")
        if isinstance(clips.get("original_sound_info"), dict)
        else {}
    )
    audio_parts = (
        original_sound.get("audio_parts")
        if isinstance(original_sound.get("audio_parts"), list)
        else []
    )
    audio_part = next((item for item in audio_parts if isinstance(item, dict)), {})
    name = _text(
        _first(info, ("song_name", "songName", "musicName", "audio_name", "title"))
        or _first(record, ("audioName", "musicName", "soundName"))
        or _first(meta, ("song_name", "musicName", "audioName"))
        or _first(audio_part, ("display_title", "title", "song_name"))
        or _first(original_sound, ("original_audio_title", "title"))
    )
    artist = _text(
        _first(info, ("artist_name", "artistName", "musicAuthor", "author"))
        or _first(record, ("musicAuthor", "audioAuthor"))
        or _first(meta, ("artist_name", "musicAuthor"))
        or _first(audio_part, ("display_artist", "artist", "artist_name"))
    )
    return {"musicName": name, "musicAuthor": artist}


def _caption_text(record: Dict) -> str:
    caption = record.get("caption")
    if isinstance(caption, dict):
        return _text(_first(caption, ("text", "caption", "title"))) or _text(
            record.get("text")
        )
    return _text(caption or record.get("text"))


def _metric_value(record: Dict, top_level_keys: Iterable[str], metric_keys: Iterable[str]) -> int:
    value = _first(record, top_level_keys, default=None)
    if value is None:
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        value = _first(metrics, metric_keys, default=0)
    return _number(value)


def _metric_available(record: Dict, top_level_keys: Iterable[str], metric_keys: Iterable[str]) -> bool:
    if any(key in record and record.get(key) is not None for key in top_level_keys):
        return True
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    return any(key in metrics and metrics.get(key) is not None for key in metric_keys)


def normalize_instagram_record(record: Dict, requested_url: str = "") -> Dict:
    """Return one Instagram item in the classifier's canonical record shape."""
    raw = dict(record or {})
    requested_url = _text(requested_url)
    public_url = _instagram_record_url(raw) or requested_url
    code = _instagram_record_shortcode(raw) or instagram_shortcode(requested_url)
    images = _image_urls(raw)
    video_url = _video_url(raw)
    type_text = _text(raw.get("type") or raw.get("media_name")).casefold()
    product_type = _text(raw.get("productType") or raw.get("product_type")).casefold()
    children = raw.get("childPosts") if isinstance(raw.get("childPosts"), list) else []
    is_slideshow = (
        type_text in {"sidecar", "carousel", "carousel_container"}
        or product_type in {"carousel", "carousel_container"}
        or len(children) >= 2
        or (not video_url and len(images) >= 2)
    )
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    creator = _text(
        _first(raw, ("ownerUsername", "username"))
        or _first(user, ("username", "user_name"))
    )
    creator_display = _text(
        _first(raw, ("ownerFullName", "fullName"))
        or _first(user, ("full_name", "fullName", "name"))
    )
    followers = _number(
        _first(raw, ("ownerFollowersCount", "followersCount", "followerCount"))
        or _nested(raw, "owner", "followersCount", default=0)
        or _first(user, ("follower_count", "followers_count", "followers"), default=0)
        or _nested(raw, "metrics", "user_follower_count", default=0)
    )
    hashtags = raw.get("hashtags") if isinstance(raw.get("hashtags"), list) else []
    caption = raw.get("caption") if isinstance(raw.get("caption"), dict) else {}
    if not hashtags and isinstance(caption.get("hashtags"), list):
        hashtags = caption.get("hashtags", [])
    if not hashtags:
        hashtags = re.findall(r"#([^\s#]+)", _caption_text(raw))
    hashtags = [_text(item).lstrip("#") for item in hashtags if _text(item)]
    cover = _text(
        _first(raw, ("displayUrl", "thumbnailUrl", "thumbnail_url"))
    ) or (images[0] if images else "")
    duration = _number(_first(raw, ("videoDuration", "duration", "video_duration")))
    music = _music(raw)

    normalized = {
        "id": _text(_first(raw, ("id", "postId", "pk"))) or code or normalize_post_url(public_url),
        "url": public_url,
        "webVideoUrl": public_url,
        "submittedVideoUrl": requested_url or public_url,
        "inputUrl": requested_url or _text(raw.get("inputUrl")) or public_url,
        "text": _caption_text(raw),
        "hashtags": hashtags,
        "playCount": _metric_value(
            raw,
            ("videoPlayCount", "videoViewCount", "viewCount", "playsCount"),
            ("play_count", "ig_play_count", "view_count"),
        ),
        "diggCount": _metric_value(
            raw, ("likesCount", "likeCount", "likes"), ("like_count",)
        ),
        "commentCount": _metric_value(
            raw, ("commentsCount", "commentCount", "comments"), ("comment_count",)
        ),
        "shareCount": _metric_value(
            raw, ("sharesCount", "shareCount", "shares"), ("share_count",)
        ),
        "collectCount": _metric_value(
            raw, ("savesCount", "saveCount", "saves"), ("save_count",)
        ),
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
        "createTimeISO": _text(
            _first(raw, ("timestamp", "takenAt", "taken_at_date", "createdAt"))
        ),
        "locationCreated": "",
        "_platform": INSTAGRAM_REELS,
        "platform": INSTAGRAM_REELS,
        "instagramShortcode": code,
        "instagramProductType": _text(raw.get("productType") or raw.get("product_type")),
        "instagramType": _text(raw.get("type") or raw.get("media_name")),
        "instagramMetricsUnavailable": [
            name
            for name, top_keys, metric_keys in (
                ("Shares", ("sharesCount", "shareCount", "shares"), ("share_count",)),
                ("Saves", ("savesCount", "saveCount", "saves"), ("save_count",)),
            )
            if not _metric_available(raw, top_keys, metric_keys)
        ],
    }
    if _text(raw.get("error")) or _text(raw.get("errorCode")):
        normalized["error"] = _text(raw.get("error"))
        normalized["errorCode"] = _text(raw.get("errorCode"))
    return normalized


# -----------------------------------------------------------------------------
# Apify execution and result matching
# -----------------------------------------------------------------------------


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

    # Data Slayer's post-details actor returns public Reel metadata plus nested
    # play, like, comment, share and save counts. Explicit Reel URLs use it as
    # the primary adapter; the broad Apify actor below remains the fallback.
    if reel_links:
        try:
            reel_items = _run_actor_items(
                client,
                INSTAGRAM_REEL_ACTOR_ID,
                {"postUrls": reel_links},
            )
        except Exception:
            # Keep tagging usable if the community actor is temporarily
            # unavailable. Missing metrics stay explicitly unavailable instead
            # of being exported as confirmed zeroes.
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
