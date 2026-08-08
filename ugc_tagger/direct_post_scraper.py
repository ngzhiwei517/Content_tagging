"""Best-effort public TikTok post retrieval without persistent media.

The direct path intentionally handles regular ``/video/`` posts only. TikTok
photo posts and any extraction failures are returned to the caller so the
existing Apify adapter can handle them without changing tagging behaviour.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple


DirectExtractor = Callable[[str], Optional[Dict]]


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
        "socket_timeout": 30,
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


def _direct_record(requested_url: str, info: Dict) -> Dict:
    canonical_url = str(info.get("webpage_url") or requested_url).strip()
    uploader_id = str(
        info.get("uploader_id")
        or info.get("channel_id")
        or info.get("uploader")
        or ""
    ).lstrip("@")
    display_name = str(info.get("uploader") or uploader_id)
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
        "collectCount": 0,
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
            "downloadAddr": canonical_url,
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
        "videoMeta.downloadAddr": canonical_url,
        "videoMeta.coverUrl": thumbnail,
        "videoMeta.originalCoverUrl": thumbnail,
        # The backend recognises the original post URL and lets yt-dlp place
        # the media directly in its TemporaryDirectory. No media is checkpointed.
        "mediaUrls": [canonical_url],
        "isSlideshow": False,
    }
    return record


def scrape_tiktok_posts_direct(
    links: Iterable[str],
    *,
    extractor: Optional[DirectExtractor] = None,
    max_workers: int = 4,
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
        return _direct_record(link, info) if _usable_video_info(info) else None

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
