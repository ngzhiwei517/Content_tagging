"""Best-effort public TikTok post retrieval without persistent media.

The direct path intentionally handles regular ``/video/`` posts only. TikTok
photo posts and any extraction failures are returned to the caller so the
existing Apify adapter can handle them without changing tagging behaviour.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re
from typing import Callable, Dict, Iterable, List, Optional, Tuple


DirectExtractor = Callable[[str], Optional[Dict]]


# Keep the free-first metadata attempt responsive. A blocked platform request
# should reach the existing Apify fallback promptly instead of holding an
# entire checkpoint window for up to 30 seconds per worker wave.
DIRECT_SCRAPE_TIMEOUT_SECONDS = 12
DIRECT_SCRAPE_MAX_WORKERS = 8
TIKTOK_OEMBED_URL = "https://www.tiktok.com/oembed"
TIKTOK_OEMBED_TIMEOUT_SECONDS = 8


def _clean_text(value) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def _record_caption(record: Dict) -> str:
    for key in (
        "text",
        "caption",
        "Caption",
        "description",
        "Description",
        "Post Caption",
        "title",
    ):
        value = _clean_text(record.get(key))
        if value:
            return value
    return ""


def _record_post_url(record: Dict) -> str:
    for key in (
        "webVideoUrl",
        "submittedVideoUrl",
        "_resolved_url",
        "url",
        "_requested_url",
    ):
        value = _clean_text(record.get(key))
        if _regular_video_url(value):
            return value
    return ""


def _caption_hashtags(caption: str) -> List[Dict[str, str]]:
    seen = set()
    hashtags = []
    for match in re.findall(r"(?<!\w)#([\w-]+)", caption, flags=re.UNICODE):
        name = match.strip().lstrip("#")
        folded = name.casefold()
        if name and folded not in seen:
            seen.add(folded)
            hashtags.append({"name": name})
    return hashtags


def enrich_tiktok_records_with_oembed(
    records: Iterable[Dict],
    *,
    http_get=None,
    max_workers: int = DIRECT_SCRAPE_MAX_WORKERS,
    timeout: int = TIKTOK_OEMBED_TIMEOUT_SECONDS,
) -> List[Dict]:
    """Fill missing TikTok captions from the public oEmbed response.

    Existing scraper values always win. The fallback retrieves public metadata
    only; it does not download media or use an API key.
    """
    output = [record for record in records if isinstance(record, dict)]
    pending = []
    for record in output:
        caption = _record_caption(record)
        if caption:
            # Normalize alternate scraper field names for downstream guardrails.
            record["text"] = caption
            if not record.get("hashtags"):
                record["hashtags"] = _caption_hashtags(caption)
            continue
        post_url = _record_post_url(record)
        if post_url:
            pending.append((record, post_url))

    if not pending:
        return output

    if http_get is None:
        import requests

        http_get = requests.get

    def fetch_caption(item):
        record, post_url = item
        try:
            response = http_get(
                TIKTOK_OEMBED_URL,
                params={"url": post_url},
                timeout=timeout,
            )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            payload = response.json()
        except Exception:
            return record, {}
        return record, payload if isinstance(payload, dict) else {}

    workers = max(1, min(int(max_workers), len(pending)))
    if len(pending) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            fetched = list(executor.map(fetch_caption, pending))
    else:
        fetched = [fetch_caption(pending[0])]

    for record, payload in fetched:
        caption = _clean_text(payload.get("title"))
        if not caption:
            continue
        record["text"] = caption
        record["hashtags"] = _caption_hashtags(caption)
        record["_caption_provider"] = "tiktok_oembed"
        author_name = _clean_text(payload.get("author_name"))
        author = record.get("authorMeta")
        if author_name and isinstance(author, dict) and not _clean_text(author.get("name")):
            author["name"] = author_name.lstrip("@")
            record["authorMeta.name"] = author_name.lstrip("@")
    return output


def _number(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _default_extract(url: str) -> Optional[Dict]:
    """Extract metadata only; the video is downloaded later to a temp folder."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("Missing dependency: install yt-dlp.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": DIRECT_SCRAPE_TIMEOUT_SECONDS,
        "retries": 1,
        "extractor_retries": 1,
        # A combined, moderate-resolution stream is sufficient for frame-based
        # tagging and avoids selecting unnecessarily large media.
        "format": "worst[height>=360]/best[height<=720]/worst",
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        result = downloader.extract_info(url, download=False)
    return result if isinstance(result, dict) else None


def _regular_video_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return "tiktok.com" in lowered and "/video/" in lowered


def _usable_video_info(info: Optional[Dict]) -> bool:
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
        return False
    return bool(info.get("id") and (info.get("url") or info.get("formats")))


def tiktok_post_has_essential_metrics(info: Optional[Dict]) -> bool:
    """Require explicit views, likes, and comments from either scraper."""
    if not isinstance(info, dict) or info.get("error") or info.get("errorCode"):
        return False

    def has_value(keys) -> bool:
        for key in keys:
            if key not in info:
                continue
            value = info.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip().casefold() in {
                "", "nan", "none", "null",
            }:
                continue
            return True
        return False

    return all(
        has_value(keys)
        for keys in (
            ("view_count", "playCount", "viewCount", "views"),
            ("like_count", "diggCount", "likeCount", "likes"),
            ("comment_count", "commentCount", "comments"),
        )
    )


def _tiktok_handle_from_url(url: str) -> str:
    match = re.search(r"tiktok\.com/@([^/?#]+)", str(url or ""), flags=re.IGNORECASE)
    return match.group(1).strip().lstrip("@") if match else ""


def _non_numeric_handle(*values) -> str:
    for value in values:
        candidate = str(value or "").strip().lstrip("@")
        if candidate and not candidate.isdigit():
            return candidate
    return ""


def _direct_record(requested_url: str, info: Dict) -> Dict:
    canonical_url = str(info.get("webpage_url") or requested_url).strip()
    direct_media_url = str(info.get("url") or "").strip()
    raw_headers = info.get("http_headers")
    media_request_headers = {}
    if isinstance(raw_headers, dict):
        # Keep only ordinary public request headers. Cookies and authorization
        # values must never enter a checkpoint or exported review payload.
        allowed_headers = {
            "accept", "accept-language", "origin", "referer", "user-agent",
        }
        media_request_headers = {
            str(key): str(value)
            for key, value in raw_headers.items()
            if str(key).strip().casefold() in allowed_headers
            and str(value or "").strip()
        }
    uploader_id = _non_numeric_handle(
        _tiktok_handle_from_url(canonical_url),
        _tiktok_handle_from_url(requested_url),
        info.get("uploader"),
        info.get("uploader_id"),
    )
    display_name = str(info.get("channel") or info.get("uploader") or uploader_id)
    thumbnail = str(info.get("thumbnail") or "")
    tags = info.get("tags") if isinstance(info.get("tags"), list) else []
    timestamp = _number(info.get("timestamp"), 0)
    create_time = timestamp
    if timestamp:
        create_time = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()

    record = {
        "id": str(info.get("id") or ""),
        "url": canonical_url,
        "webVideoUrl": canonical_url,
        "submittedVideoUrl": requested_url,
        "_requested_url": requested_url,
        "_resolved_url": canonical_url,
        "_platform": "TikTok",
        "platform": "TikTok",
        "_scrape_provider": "direct_yt_dlp",
        "text": str(info.get("description") or info.get("title") or ""),
        "createTime": create_time,
        "playCount": _number(info.get("view_count")),
        "diggCount": _number(info.get("like_count")),
        "commentCount": _number(info.get("comment_count")),
        "shareCount": _number(info.get("repost_count")),
        "collectCount": _number(info.get("save_count")),
        "authorMeta": {
            "name": uploader_id,
            "nickName": display_name,
            "fans": _number(info.get("channel_follower_count")),
        },
        "hashtags": [{"name": str(tag).lstrip("#")} for tag in tags if str(tag).strip()],
        "musicMeta": {
            "musicName": str(info.get("track") or ""),
            "musicAuthor": str(info.get("artist") or ""),
        },
        "videoMeta": {
            "duration": info.get("duration") or 0,
            "width": info.get("width") or 0,
            "height": info.get("height") or 0,
            # Reuse the media URL resolved by this metadata extraction. The
            # backend falls back to the public post URL if this temporary URL
            # expires before a resumed chunk downloads it.
            "downloadAddr": direct_media_url or canonical_url,
            "fallbackDownloadAddr": canonical_url,
            "coverUrl": thumbnail,
            "originalCoverUrl": thumbnail,
            "webVideoUrl": canonical_url,
        },
        "authorMeta.name": uploader_id,
        "authorMeta.nickName": display_name,
        "authorMeta.fans": _number(info.get("channel_follower_count")),
        "musicMeta.musicName": str(info.get("track") or ""),
        "musicMeta.musicAuthor": str(info.get("artist") or ""),
        "videoMeta.duration": info.get("duration") or 0,
        "videoMeta.width": info.get("width") or 0,
        "videoMeta.height": info.get("height") or 0,
        "videoMeta.downloadAddr": direct_media_url or canonical_url,
        "videoMeta.fallbackDownloadAddr": canonical_url,
        "videoMeta.coverUrl": thumbnail,
        "videoMeta.originalCoverUrl": thumbnail,
        "mediaUrls": [direct_media_url or canonical_url],
        "mediaRequestHeaders": media_request_headers,
        "isSlideshow": False,
    }
    return record


def scrape_tiktok_posts_direct(
    links: Iterable[str],
    *,
    extractor: Optional[DirectExtractor] = None,
    max_workers: int = DIRECT_SCRAPE_MAX_WORKERS,
) -> Tuple[List[Dict], List[str]]:
    """Return ``(records, fallback_links)`` while preserving input order."""
    requested = [str(link or "").strip() for link in links if str(link or "").strip()]
    extractor = extractor or _default_extract

    def extract_one(link: str):
        if not _regular_video_url(link):
            return None
        try:
            info = extractor(link)
        except Exception:
            return None
        if not _usable_video_info(info) or not tiktok_post_has_essential_metrics(info):
            return None
        return _direct_record(link, info)

    if len(requested) > 1:
        workers = max(1, min(int(max_workers), len(requested)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            extracted = list(executor.map(extract_one, requested))
    else:
        extracted = [extract_one(link) for link in requested]

    records = [record for record in extracted if isinstance(record, dict)]
    fallback_links = [
        link for link, record in zip(requested, extracted) if not isinstance(record, dict)
    ]
    return records, fallback_links
