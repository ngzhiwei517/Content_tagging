"""Optional public creator-profile enrichment for the marketing dashboard.

This module deliberately retrieves metadata only. It never requests media
downloads and never persists the Apify token or returned post media URLs.
"""

from __future__ import annotations

import json
import random
import re
import string
import time
from datetime import datetime, timezone
from html import unescape
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import pandas as pd

from ugc_tagger.instagram_reels_adapter import INSTAGRAM_REELS, TIKTOK


TIKTOK_PROFILE_ACTOR_ID = "clockworks/tiktok-scraper"
INSTAGRAM_PROFILE_ACTOR_ID = "apify/instagram-scraper"
DEFAULT_PROFILE_POST_LIMIT = 20
FULL_PROFILE_POST_CEILING = 2000
INSTAGRAM_APIFY_FALLBACK_POST_LIMIT = 20
PROFILE_HISTORY_LATEST = "Latest 20 (fast)"
PROFILE_HISTORY_FULL = "Full 3 months"
PROFILE_HISTORY_OPTIONS = (PROFILE_HISTORY_LATEST, PROFILE_HISTORY_FULL)
DEFAULT_PROFILE_HISTORY_MODE = PROFILE_HISTORY_LATEST
PROFILE_SCOPE_OPTIONS = ("Top 5", "Top 10", "Top 20")
DIRECT_PROFILE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
TIKTOK_PROFILE_STATS_URL = "https://www.tiktok.com/api/creator/item_list/"
FOLLOWER_LOOKUP_TIMEOUT_SECONDS = 8

PROFILE_METRIC_COLUMNS = [
    "Platform",
    "Creator Key",
    "Profile Creator",
    "Creator Profile",
    "Profile Posts",
    "Current Followers",
    "Profile Average Views",
    "Profile Average Engagement",
    "Profile Average Engagement Rate",
    "Profile Data Status",
]


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def _number(value) -> int:
    try:
        number = int(float(str(value).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _optional_number(value):
    """Return a non-negative number while preserving an unavailable value."""
    raw = _text(value)
    if not raw:
        return pd.NA
    try:
        number = int(float(raw.replace(",", "")))
    except (TypeError, ValueError):
        return pd.NA
    return max(number, 0)


def _nested(record: Dict, *path, default=None):
    current = record
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
    return default if current is None else current


def _first(record: Dict, keys: Iterable[str], default=None):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_creator_handle(value) -> str:
    """Return a platform username without URL syntax or a leading @ sign."""
    raw = _text(value)
    if not raw:
        return ""
    if "://" in raw:
        try:
            path = urlsplit(raw).path.strip("/")
            if path:
                raw = path.split("/", 1)[0]
        except ValueError:
            return ""
    return raw.strip().lstrip("@").strip()


def creator_key(value) -> str:
    return normalize_creator_handle(value).casefold()


def creator_profile_url(platform: str, creator) -> str:
    """Build the public profile URL used by the clickable dashboard column."""
    handle = normalize_creator_handle(creator)
    if not handle:
        return ""
    safe_handle = quote(handle, safe="._-")
    if _text(platform).casefold().startswith("instagram"):
        return f"https://www.instagram.com/{safe_handle}/"
    return f"https://www.tiktok.com/@{safe_handle}"


def profile_scope_count(scope: str, total: int) -> int:
    if _text(scope) == "Top 5":
        return min(5, max(int(total), 0))
    if _text(scope) == "Top 10":
        return min(10, max(int(total), 0))
    if _text(scope) == "Top 20":
        return min(20, max(int(total), 0))
    # Unknown or retired values such as "All" must fail to the least costly
    # option instead of unexpectedly requesting every creator profile.
    return min(5, max(int(total), 0))


def profile_history_settings(
    history_mode: str,
    post_limit: int = DEFAULT_PROFILE_POST_LIMIT,
) -> Tuple[str, int]:
    """Return a recognized history mode and its enforced metadata-only limit.

    Unknown values deliberately fall back to the least expensive existing
    behavior. Full-history mode always uses its fixed emergency ceiling so a
    caller cannot accidentally request an unbounded profile crawl.
    """
    if _text(history_mode) == PROFILE_HISTORY_FULL:
        return PROFILE_HISTORY_FULL, FULL_PROFILE_POST_CEILING
    try:
        safe_limit = int(post_limit)
    except (TypeError, ValueError):
        safe_limit = DEFAULT_PROFILE_POST_LIMIT
    return PROFILE_HISTORY_LATEST, min(
        max(safe_limit, 1),
        DEFAULT_PROFILE_POST_LIMIT,
    )


def _dataset_id(run) -> str:
    if isinstance(run, dict):
        return _text(run.get("defaultDatasetId") or run.get("default_dataset_id"))
    return _text(
        getattr(run, "default_dataset_id", None)
        or getattr(run, "defaultDatasetId", None)
    )


def _run_actor_items(client, actor_id: str, run_input: Dict) -> List[Dict]:
    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = _dataset_id(run)
    if not dataset_id:
        raise RuntimeError("Actor completed without a dataset.")
    return [item for item in client.dataset(dataset_id).iterate_items() if isinstance(item, dict)]


def _tiktok_post_row(record: Dict) -> Dict:
    author = record.get("authorMeta") if isinstance(record.get("authorMeta"), dict) else {}
    creator = _text(
        _first(author, ("name", "uniqueId", "username"))
        or _first(record, ("author", "username", "creator"))
    )
    followers = _number(
        _first(author, ("fans", "followers", "followerCount", "fansCount"), 0)
    )
    views = _number(_first(record, ("playCount", "viewCount", "views"), 0))
    engagement = sum(
        _number(_first(record, keys, 0))
        for keys in (
            ("diggCount", "likeCount", "likes"),
            ("commentCount", "comments"),
            ("shareCount", "shares"),
            ("collectCount", "saveCount", "saves"),
        )
    )
    post_date = _first(record, ("createTimeISO", "createdAt", "timestamp", "createTime"))
    return {
        "Platform": TIKTOK,
        "Creator": creator,
        "Creator Key": creator_key(creator),
        "Post Date": post_date,
        "Followers": followers,
        "Views": views,
        "Engagement": engagement,
        "Engagement Rate": (engagement / views * 100) if views else pd.NA,
    }


def _instagram_post_row(record: Dict) -> Dict:
    user = record.get("user") if isinstance(record.get("user"), dict) else {}
    creator = _text(
        _first(record, ("ownerUsername", "owner_username", "username"))
        or _first(user, ("username", "user_name"))
    )
    followers = _number(
        _first(record, ("ownerFollowersCount", "followersCount", "followerCount"), 0)
        or _nested(record, "owner", "followersCount", default=0)
        or _first(user, ("follower_count", "followers_count", "followers"), 0)
    )
    views = _optional_number(
        _first(
            record,
            ("videoPlayCount", "videoViewCount", "viewCount", "playCount", "viewsCount"),
        )
    )
    media_type = " ".join(
        _text(record.get(key)).casefold()
        for key in ("type", "mediaType", "productType")
        if _text(record.get(key))
    )
    is_non_video = (
        record.get("isVideo") is False
        or any(marker in media_type for marker in ("image", "sidecar", "carousel"))
    )
    # Instagram/Apify can return videoPlayCount=0 for image and carousel posts.
    # That is a schema placeholder rather than a measured zero view count.
    if pd.notna(views) and views == 0 and is_non_video:
        views = pd.NA
    engagement = sum(
        _number(_first(record, keys, 0))
        for keys in (
            ("likesCount", "likeCount", "likes"),
            ("commentsCount", "commentCount", "comments"),
            ("sharesCount", "shareCount", "shares"),
            ("savesCount", "saveCount", "saves"),
        )
    )
    return {
        "Platform": INSTAGRAM_REELS,
        "Creator": creator,
        "Creator Key": creator_key(creator),
        "Post Date": _first(
            record,
            ("timestamp", "posted_at", "takenAt", "taken_at_date", "taken_at_timestamp", "createdAt"),
        ),
        "Followers": followers,
        "Views": views,
        "Engagement": engagement,
        "Engagement Rate": (
            engagement / views * 100
            if pd.notna(views) and views > 0
            else pd.NA
        ),
    }


def _instagram_profile_followers(items: Iterable[Dict]) -> Dict[str, int]:
    followers_by_creator: Dict[str, int] = {}
    for item in items:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        handle = _text(
            _first(item, ("username", "ownerUsername", "profileName", "userName"))
            or _first(user, ("username", "user_name"))
        )
        key = creator_key(handle)
        if not key:
            continue
        followers_by_creator[key] = max(
            followers_by_creator.get(key, 0),
            _number(
                _first(item, ("followersCount", "followers", "followerCount", "followers_count"), 0)
                or _first(user, ("follower_count", "followers_count", "followers"), 0)
            ),
        )
    return followers_by_creator


def _recursive_first(record, keys: Iterable[str]):
    """Find the first non-empty value for any key in nested JSON data."""
    if isinstance(record, dict):
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        for value in record.values():
            found = _recursive_first(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(record, list):
        for value in record:
            found = _recursive_first(value, keys)
            if found not in (None, ""):
                return found
    return None


def _nested_dicts(record):
    """Yield every dictionary in a decoded hydration payload."""
    if isinstance(record, dict):
        yield record
        for value in record.values():
            yield from _nested_dicts(value)
    elif isinstance(record, list):
        for value in record:
            yield from _nested_dicts(value)


def _tiktok_matched_profile_details(
    payload: Dict,
    expected_creator: str,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Return fields paired with the requested creator inside hydration JSON."""
    expected_key = creator_key(expected_creator)
    if not expected_key:
        return "", None, None

    def paired_details(user, stats=None, fallback_handle=""):
        if not isinstance(user, dict):
            return None
        returned_key = creator_key(
            _first(
                user,
                ("uniqueId", "unique_id", "username", "userName"),
                fallback_handle,
            )
        )
        if returned_key != expected_key:
            return None
        sec_uid = _text(_first(user, ("secUid", "sec_uid", "authorSecId"), ""))
        if not sec_uid:
            return None
        stats_record = stats if isinstance(stats, dict) else user
        follower_value = _first(
            stats_record,
            ("followerCount", "followersCount", "follower_count"),
            None,
        )
        post_count_value = _first(
            stats_record,
            ("videoCount", "postCount", "video_count", "post_count"),
            None,
        )
        return (
            sec_uid,
            _number(follower_value) if follower_value not in (None, "") else None,
            _number(post_count_value) if post_count_value not in (None, "") else None,
        )

    for scope in _nested_dicts(payload):
        # Common userInfo shape: {"user": {...}, "stats": {...}}.
        direct = paired_details(scope.get("user"), scope.get("stats"))
        if direct:
            return direct

        # SIGI_STATE commonly keeps users and their stats in sibling maps.
        users = scope.get("users")
        stats_by_user = scope.get("stats")
        if isinstance(users, dict):
            for map_key, user in users.items():
                paired_stats = (
                    stats_by_user.get(map_key)
                    if isinstance(stats_by_user, dict)
                    else None
                )
                mapped = paired_details(user, paired_stats, fallback_handle=map_key)
                if mapped:
                    return mapped

        # Some payloads place identity and statistics in the same object.
        inline = paired_details(
            scope,
            scope.get("stats") if isinstance(scope.get("stats"), dict) else scope,
        )
        if inline:
            return inline
    return "", None, None


def _tiktok_profile_header_details(
    page_html: str,
    *,
    expected_creator: str = "",
) -> Tuple[str, Optional[int], Optional[int]]:
    """Extract TikTok profile-header fields while preserving missing values."""
    source = _text(page_html)
    if not source:
        return "", None, None

    payloads = []
    for script_id in ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
        match = re.search(
            rf'<script[^>]+id=["\']{re.escape(script_id)}["\'][^>]*>(.*?)</script>',
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        try:
            payloads.append(json.loads(unescape(match.group(1)).strip()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    for payload in payloads:
        if expected_creator:
            matched = _tiktok_matched_profile_details(payload, expected_creator)
            if matched[0]:
                return matched
            continue
        sec_uid = _text(_recursive_first(payload, ("secUid", "sec_uid")))
        follower_value = _recursive_first(
            payload,
            ("followerCount", "followersCount", "follower_count"),
        )
        post_count_value = _recursive_first(
            payload,
            ("videoCount", "postCount", "video_count", "post_count"),
        )
        if sec_uid:
            followers = (
                _number(follower_value)
                if follower_value not in (None, "")
                else None
            )
            post_count = (
                _number(post_count_value)
                if post_count_value not in (None, "")
                else None
            )
            return sec_uid, followers, post_count

    # TikTok occasionally moves the hydration payload while retaining these
    # public JSON fields. Keep a narrow fallback rather than storing the page.
    # It is intentionally disabled for follower-only lookups because raw
    # fields cannot prove that the identity and statistics belong together.
    if expected_creator:
        return "", None, None
    sec_uid_match = re.search(r'["\']secUid["\']\s*:\s*["\']([^"\']+)', source)
    follower_match = re.search(
        r'["\'](?:followerCount|followersCount)["\']\s*:\s*(\d+)',
        source,
    )
    post_count_match = re.search(
        r'["\'](?:videoCount|postCount)["\']\s*:\s*(\d+)',
        source,
    )
    return (
        _text(sec_uid_match.group(1) if sec_uid_match else ""),
        _number(follower_match.group(1)) if follower_match else None,
        _number(post_count_match.group(1)) if post_count_match else None,
    )


def _tiktok_profile_details(page_html: str) -> Tuple[str, int, Optional[int]]:
    """Extract a public TikTok profile's secUid, followers, and post count."""
    sec_uid, followers, post_count = _tiktok_profile_header_details(page_html)
    return sec_uid, followers if followers is not None else 0, post_count


def _fetch_tiktok_profile_html(profile_url: str, *, timeout: int = 20) -> str:
    """Retrieve public profile HTML without cookies, proxies, or media."""
    import requests

    response = requests.get(
        profile_url,
        headers={
            "User-Agent": DIRECT_PROFILE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _fetch_tiktok_profile_stats(sec_uid: str, creator: str) -> Dict:
    """Fetch one public TikTok profile item to read its author statistics."""
    import requests

    query = {
        "aid": "1988",
        "app_language": "en",
        "app_name": "tiktok_web",
        "browser_language": "en-US",
        "browser_name": "Mozilla",
        "browser_online": "true",
        "browser_platform": "Win32",
        "browser_version": "5.0 (Windows)",
        "channel": "tiktok_web",
        "cookie_enabled": "true",
        "count": "1",
        "cursor": str(int(time.time() * 1000)),
        "device_id": "".join(random.choices(string.digits, k=19)),
        "device_platform": "web_pc",
        "focus_state": "true",
        "from_page": "user",
        "history_len": "2",
        "is_fullscreen": "false",
        "is_page_visible": "true",
        "language": "en",
        "os": "windows",
        "region": "US",
        "screen_height": "1080",
        "screen_width": "1920",
        "secUid": sec_uid,
        "type": "1",
        "tz_name": "UTC",
        "verifyFp": "verify_" + "".join(random.choices(string.hexdigits, k=7)),
        "webcast_language": "en",
    }
    response = requests.get(
        TIKTOK_PROFILE_STATS_URL,
        params=query,
        headers={
            "User-Agent": DIRECT_PROFILE_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": creator_profile_url(TIKTOK, creator),
        },
        timeout=FOLLOWER_LOOKUP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("TikTok profile statistics were not available.")
    return payload


def _extract_tiktok_post_identity(post_url: str) -> Dict:
    """Resolve a TikTok post's creator identity without downloading media."""
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("Missing dependency: install yt-dlp.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "socket_timeout": FOLLOWER_LOOKUP_TIMEOUT_SECONDS,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(post_url, download=False)
    return info if isinstance(info, dict) else {}


def resolve_tiktok_creator_handle(
    creator,
    representative_post_url: str,
    *,
    post_extractor: Optional[Callable[[str], Dict]] = None,
) -> str:
    """Resolve a renamed TikTok creator from one of their live post URLs.

    The post URL is already associated with the ranked creator in the current
    batch.  Only a public username returned by the live post extractor is
    accepted; numeric account IDs and display names containing spaces are
    rejected.  No media is downloaded.
    """
    original = normalize_creator_handle(creator)
    post_url = _text(representative_post_url)
    if not post_url:
        raise RuntimeError("A representative TikTok post URL is required.")
    extract_post_identity = post_extractor or _extract_tiktok_post_identity
    try:
        info = extract_post_identity(post_url)
    except Exception as exc:
        raise RuntimeError("TikTok post identity could not be retrieved.") from exc
    if not isinstance(info, dict):
        raise RuntimeError("TikTok post identity was not available.")

    author_meta = info.get("authorMeta")
    if not isinstance(author_meta, dict):
        author_meta = {}
    author = info.get("author")
    if not isinstance(author, dict):
        author = {}

    url_candidates = [
        info.get("uploader_url"),
        info.get("channel_url"),
        info.get("webpage_url"),
        info.get("original_url"),
    ]
    candidates = [
        info.get("uploader_id"),
        author_meta.get("name"),
        author_meta.get("uniqueId"),
        author.get("uniqueId"),
        author.get("username"),
    ]
    for value in url_candidates:
        match = re.search(r"tiktok\.com/@([^/?#]+)", _text(value), re.IGNORECASE)
        if match:
            candidates.append(match.group(1))
    # ``uploader`` and ``channel`` are last because yt-dlp may use a display
    # name there. The strict username pattern prevents accepting that label.
    candidates.extend([info.get("uploader"), info.get("channel")])

    for value in candidates:
        candidate = normalize_creator_handle(value)
        if (
            candidate
            and not candidate.isdigit()
            and re.fullmatch(r"[A-Za-z0-9._]{2,30}", candidate)
        ):
            return candidate
    if original:
        raise RuntimeError(f"TikTok did not return a current username for @{original}.")
    raise RuntimeError("TikTok did not return a current username.")


def _tiktok_profile_stats_followers(
    payload: Dict,
    *,
    expected_creator: str,
    expected_sec_uid: str,
) -> Optional[int]:
    """Read followers only when the returned author matches the target."""
    expected_key = creator_key(expected_creator)
    for item in list((payload or {}).get("itemList") or []):
        if not isinstance(item, dict):
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        returned_key = creator_key(
            _first(author, ("uniqueId", "unique_id", "author"), "")
        )
        returned_sec_uid = _text(
            _first(author, ("secUid", "sec_uid", "authorSecId"), "")
        )
        if returned_key and expected_key and returned_key != expected_key:
            continue
        if returned_sec_uid and expected_sec_uid and returned_sec_uid != expected_sec_uid:
            continue
        if not (
            (returned_key and returned_key == expected_key)
            or (returned_sec_uid and returned_sec_uid == expected_sec_uid)
        ):
            continue
        stats = item.get("authorStats")
        if not isinstance(stats, dict):
            stats = item.get("authorStatsV2")
        if not isinstance(stats, dict):
            continue
        follower_value = _first(
            stats,
            ("followerCount", "followersCount", "follower_count"),
            None,
        )
        if follower_value not in (None, ""):
            return _number(follower_value)
    return None


def fetch_tiktok_profile_followers(
    creator,
    *,
    representative_post_url: str = "",
    profile_fetcher: Optional[Callable[[str], str]] = None,
    post_extractor: Optional[Callable[[str], Dict]] = None,
    playlist_extractor: Optional[Callable[[str, int], Dict]] = None,
    profile_stats_fetcher: Optional[Callable[[str, str], Dict]] = None,
) -> int:
    """Return one TikTok creator's public follower count without media.

    The fast path reads the public profile header. If TikTok omits that header,
    the fallback resolves the creator ID through yt-dlp and requests one public
    metadata item for its author statistics. Neither path downloads media or
    calls Apify.
    """
    handle = normalize_creator_handle(creator)
    if not handle:
        raise RuntimeError("TikTok creator handle is missing.")
    fetch_profile_html = profile_fetcher or (
        lambda profile_url: _fetch_tiktok_profile_html(
            profile_url,
            timeout=FOLLOWER_LOOKUP_TIMEOUT_SECONDS,
        )
    )
    try:
        page_html = fetch_profile_html(creator_profile_url(TIKTOK, handle))
    except Exception:
        page_html = ""
    sec_uid, followers, _post_count = _tiktok_profile_header_details(
        page_html,
        expected_creator=handle,
    )
    if sec_uid and followers is not None:
        return followers

    extract_playlist = playlist_extractor or _extract_tiktok_user_playlist
    extract_post_identity = post_extractor or _extract_tiktok_post_identity
    fetch_profile_stats = profile_stats_fetcher or _fetch_tiktok_profile_stats
    try:
        if not sec_uid and _text(representative_post_url):
            post_info = extract_post_identity(_text(representative_post_url))
            post_creator = creator_key(
                _first(post_info, ("uploader", "creator", "author"), "")
            )
            post_sec_uid = _text(
                _first(post_info, ("channel_id", "authorSecId", "secUid"), "")
            )
            if post_creator == creator_key(handle) and post_sec_uid:
                sec_uid = post_sec_uid
        if not sec_uid:
            playlist = extract_playlist(creator_profile_url(TIKTOK, handle), 1)
            if not isinstance(playlist, dict):
                raise RuntimeError("TikTok creator ID was not available.")
            sec_uid = _text(playlist.get("id"))
        if not sec_uid:
            raise RuntimeError("TikTok creator ID was not available.")
        stats_payload = fetch_profile_stats(sec_uid, handle)
        followers = _tiktok_profile_stats_followers(
            stats_payload,
            expected_creator=handle,
            expected_sec_uid=sec_uid,
        )
    except Exception as exc:
        raise RuntimeError(
            f"TikTok creator @{handle} could not be retrieved in this run."
        ) from exc
    if followers is None:
        raise RuntimeError(
            f"TikTok creator @{handle} did not return a verified follower count."
        )
    return followers


def _extract_tiktok_user_playlist(query: str, post_limit: int) -> Dict:
    """Run yt-dlp lazily in flat-playlist, metadata-only mode."""
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("Missing dependency: install yt-dlp.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": min(max(int(post_limit), 1), DEFAULT_PROFILE_POST_LIMIT),
        "ignoreerrors": True,
        "socket_timeout": 15,
        "extractor_retries": 2,
        "retries": 2,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        result = downloader.extract_info(query, download=False)
    return result if isinstance(result, dict) else {}


def _yt_dlp_post_date(entry: Dict):
    timestamp = _first(entry, ("timestamp", "release_timestamp"))
    if timestamp not in (None, ""):
        return timestamp
    compact_date = _text(_first(entry, ("upload_date", "release_date")))
    if re.fullmatch(r"\d{8}", compact_date):
        try:
            return datetime.strptime(compact_date, "%Y%m%d").date().isoformat()
        except ValueError:
            return ""
    return compact_date


def _yt_dlp_tiktok_post_row(
    entry: Dict,
    *,
    creator: str,
    followers: int,
) -> Dict:
    views = _number(
        _first(entry, ("view_count", "viewCount", "play_count", "playCount", "views"), 0)
    )
    engagement = sum(
        _number(_first(entry, keys, 0))
        for keys in (
            ("like_count", "likeCount", "diggCount", "likes"),
            ("comment_count", "commentCount", "comments"),
            ("repost_count", "share_count", "shareCount", "shares"),
            ("save_count", "collect_count", "collectCount", "saves"),
        )
    )
    return {
        "Platform": TIKTOK,
        "Creator": creator,
        "Creator Key": creator_key(creator),
        "Post Date": _yt_dlp_post_date(entry),
        "Followers": _number(followers),
        "Views": views,
        "Engagement": engagement,
        "Engagement Rate": (engagement / views * 100) if views else pd.NA,
    }


def _parse_post_dates(values: pd.Series) -> pd.Series:
    """Parse mixed ISO strings and Unix timestamps into UTC datetimes."""
    parsed = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    numeric = pd.to_numeric(values, errors="coerce")
    unix_mask = numeric.notna() & numeric.between(1_000_000_000, 99_999_999_999)
    if unix_mask.any():
        parsed.loc[unix_mask] = pd.to_datetime(
            numeric.loc[unix_mask], unit="s", errors="coerce", utc=True
        )
    return parsed


def _utc_timestamp(value=None) -> pd.Timestamp:
    """Normalize one date-like value to a timezone-aware UTC timestamp."""
    effective = datetime.now(timezone.utc) if value is None else value
    parsed = _parse_post_dates(pd.Series([effective])).iloc[0]
    if pd.isna(parsed):
        raise ValueError("A valid UTC date is required.")
    return pd.Timestamp(parsed).tz_convert("UTC")


def _full_profile_entry_identity(entry: Dict) -> str:
    return _text(_first(entry, ("id", "display_id", "webpage_url", "url")))


def _metadata_only_tiktok_entry(entry: Dict) -> Dict:
    """Keep only fields needed for aggregation; discard all media metadata."""
    permitted_fields = (
        "id",
        "display_id",
        "timestamp",
        "release_timestamp",
        "upload_date",
        "release_date",
        "view_count",
        "viewCount",
        "play_count",
        "playCount",
        "views",
        "like_count",
        "likeCount",
        "diggCount",
        "likes",
        "comment_count",
        "commentCount",
        "comments",
        "repost_count",
        "share_count",
        "shareCount",
        "shares",
        "save_count",
        "collect_count",
        "collectCount",
        "saves",
    )
    return {field: entry[field] for field in permitted_fields if field in entry}


def _collect_tiktok_full_window(
    source_entries,
    *,
    cutoff_utc,
    as_of_utc,
    cap: int = FULL_PROFILE_POST_CEILING,
) -> Dict:
    """Collect newest-to-oldest metadata until the exact UTC cutoff.

    The return contract is intentionally small and deterministic so callers
    and tests never need to retain yt-dlp's raw playlist result::

        {"entries": list[dict], "complete": bool, "partial_reason": str}

    A cap is considered reached only after seeing a cap+1th distinct, dated,
    in-window post. Exactly ``cap`` posts followed by the cutoff or natural
    exhaustion is therefore still a complete result.
    """
    cutoff = _utc_timestamp(cutoff_utc)
    effective_as_of = _utc_timestamp(as_of_utc)
    if cutoff > effective_as_of:
        raise ValueError("The profile cutoff cannot be after the as-of date.")
    try:
        safe_cap = min(max(int(cap), 1), FULL_PROFILE_POST_CEILING)
    except (TypeError, ValueError):
        safe_cap = FULL_PROFILE_POST_CEILING

    collected: List[Dict] = []
    seen_post_ids = set()
    partial_reasons: List[str] = []
    previous_timestamp: Optional[pd.Timestamp] = None
    page_error = False

    def mark_partial(reason: str) -> None:
        if reason not in partial_reasons:
            partial_reasons.append(reason)

    try:
        iterator = iter(source_entries if source_entries is not None else [])
        for entry in iterator:
            if not isinstance(entry, dict):
                page_error = True
                mark_partial("some profile pages could not be read")
                continue

            post_date = _yt_dlp_post_date(entry)
            try:
                post_timestamp = _utc_timestamp(post_date)
            except (TypeError, ValueError):
                mark_partial("some posts had no publish date")
                continue

            # Future-dated records cannot belong to the requested history.
            if post_timestamp > effective_as_of:
                continue

            identity = _full_profile_entry_identity(entry)
            if identity and identity in seen_post_ids:
                continue
            if identity:
                seen_post_ids.add(identity)

            if previous_timestamp is not None and post_timestamp > previous_timestamp:
                mark_partial("post order could not be verified")
            previous_timestamp = post_timestamp

            if post_timestamp < cutoff:
                break

            if len(collected) >= safe_cap:
                mark_partial(
                    f"{safe_cap}-post safety limit reached"
                )
                break

            collected.append(_metadata_only_tiktok_entry(entry))
    except Exception as exc:
        page_error = True
        mark_partial("some profile pages could not be read")
        if not collected:
            raise RuntimeError("TikTok profile pages could not be read.") from exc

    if page_error and not collected:
        raise RuntimeError("TikTok profile pages could not be read.")

    reason = "; ".join(partial_reasons)
    return {
        "entries": collected,
        "complete": not bool(partial_reasons),
        "partial_reason": reason,
    }


def _extract_tiktok_user_full_window(
    query: str,
    cutoff_utc,
    as_of_utc,
    cap: int = FULL_PROFILE_POST_CEILING,
) -> Dict:
    """Run a lazy, metadata-only TikTok profile crawl for a full date window."""
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("Missing dependency: install yt-dlp.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "lazy_playlist": True,
        "cachedir": False,
        "allow_playlist_files": False,
        "ignoreerrors": False,
        "socket_timeout": 15,
        "extractor_retries": 2,
        "retries": 2,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        result = downloader.extract_info(
            query,
            download=False,
            process=False,
        )
        if not isinstance(result, dict):
            raise RuntimeError("TikTok profile posts were not available.")
        return _collect_tiktok_full_window(
            result.get("entries"),
            cutoff_utc=cutoff_utc,
            as_of_utc=as_of_utc,
            cap=cap,
        )


def _extract_instagram_user_full_window(
    handle: str,
    cutoff_utc,
    as_of_utc,
    cap: int = FULL_PROFILE_POST_CEILING,
) -> Dict:
    """Collect public Instagram profile metadata without downloading media."""
    try:
        import instaloader
    except Exception as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("Missing dependency: install instaloader.") from exc

    cutoff = _utc_timestamp(cutoff_utc)
    effective_as_of = _utc_timestamp(as_of_utc)
    safe_cap = min(max(int(cap), 1), FULL_PROFILE_POST_CEILING)
    loader = instaloader.Instaloader(
        sleep=False,
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=1,
        request_timeout=20,
        resume_prefix=None,
        check_resume_bbd=False,
        iphone_support=False,
    )
    try:
        profile = instaloader.Profile.from_username(loader.context, handle)
        followers = _number(getattr(profile, "followers", 0))
        entries: List[Dict] = []
        complete = True
        partial_reason = ""
        for post in profile.get_posts():
            post_date = getattr(post, "date_utc", None)
            try:
                post_timestamp = _utc_timestamp(post_date)
            except (TypeError, ValueError):
                complete = False
                partial_reason = "some posts had no publish date"
                continue
            if post_timestamp > effective_as_of:
                continue
            if post_timestamp < cutoff:
                break
            if len(entries) >= safe_cap:
                complete = False
                partial_reason = f"{safe_cap}-post safety limit reached"
                break
            entry = {
                "id": _text(getattr(post, "mediaid", "")),
                "shortCode": _text(getattr(post, "shortcode", "")),
                "ownerUsername": handle,
                "ownerFollowersCount": followers,
                "timestamp": post_date,
                "likesCount": _number(getattr(post, "likes", 0)),
                "commentsCount": _number(getattr(post, "comments", 0)),
            }
            video_views = _optional_number(
                getattr(post, "video_view_count", None)
            )
            if pd.notna(video_views):
                entry["videoViewCount"] = video_views
            entries.append(entry)
        return {
            "followers": followers,
            "entries": entries,
            "complete": complete,
            "partial_reason": partial_reason,
        }
    except Exception as exc:
        raise RuntimeError("Instagram profile posts were not available anonymously.") from exc


def _requested_creator_frame(creators) -> pd.DataFrame:
    if isinstance(creators, pd.DataFrame):
        frame = creators.copy()
    else:
        frame = pd.DataFrame(list(creators or []))
    for column in ("Platform", "Creator"):
        if column not in frame.columns:
            frame[column] = ""
    frame["Platform"] = frame["Platform"].map(_text)
    frame["Profile Creator"] = frame["Creator"].map(normalize_creator_handle)
    frame["Creator Key"] = frame["Profile Creator"].map(creator_key)
    frame = frame[
        frame["Platform"].isin({TIKTOK, INSTAGRAM_REELS})
        & frame["Creator Key"].ne("")
    ].drop_duplicates(["Platform", "Creator Key"])
    frame["Creator Profile"] = frame.apply(
        lambda row: creator_profile_url(row["Platform"], row["Profile Creator"]),
        axis=1,
    )
    return frame[["Platform", "Creator Key", "Profile Creator", "Creator Profile"]].reset_index(drop=True)


def _aggregate_profile_posts(
    requested: pd.DataFrame,
    post_rows: List[Dict],
    *,
    instagram_followers: Optional[Dict[str, int]] = None,
    profile_followers: Optional[Dict[Tuple[str, str], int]] = None,
    failed_platforms: Optional[Iterable[str]] = None,
    failed_creators: Optional[Iterable[Tuple[str, str]]] = None,
    months: int = 3,
    as_of=None,
) -> pd.DataFrame:
    base = requested.copy()
    if base.empty:
        return pd.DataFrame(columns=PROFILE_METRIC_COLUMNS)

    posts = pd.DataFrame(post_rows)
    if not posts.empty:
        posts["Parsed Date"] = _parse_post_dates(posts["Post Date"])
        effective_as_of = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(datetime.now(timezone.utc))
        if effective_as_of.tzinfo is None:
            effective_as_of = effective_as_of.tz_localize("UTC")
        else:
            effective_as_of = effective_as_of.tz_convert("UTC")
        cutoff = effective_as_of - pd.DateOffset(months=max(int(months), 1))
        posts = posts[posts["Parsed Date"].between(cutoff, effective_as_of, inclusive="both")].copy()

    if posts.empty:
        aggregated = pd.DataFrame(columns=[
            "Platform", "Creator Key", "Profile Posts", "Current Followers",
            "Profile Average Views", "Profile Average Engagement",
            "Profile Average Engagement Rate",
        ])
    else:
        aggregated = posts.groupby(["Platform", "Creator Key"], dropna=False).agg(
            Profile_Posts=("Creator Key", "size"),
            Current_Followers=("Followers", "max"),
            Profile_Average_Views=("Views", "mean"),
            Profile_Average_Engagement=("Engagement", "mean"),
            Profile_Average_Engagement_Rate=("Engagement Rate", "mean"),
        ).reset_index().rename(columns={
            "Profile_Posts": "Profile Posts",
            "Current_Followers": "Current Followers",
            "Profile_Average_Views": "Profile Average Views",
            "Profile_Average_Engagement": "Profile Average Engagement",
            "Profile_Average_Engagement_Rate": "Profile Average Engagement Rate",
        })

    summary = base.merge(aggregated, on=["Platform", "Creator Key"], how="left")
    instagram_followers = instagram_followers or {}
    profile_followers = profile_followers or {}
    instagram_mask = summary["Platform"].eq(INSTAGRAM_REELS)
    direct_followers = summary.apply(
        lambda row: _number(
            profile_followers.get((row["Platform"], row["Creator Key"]), 0)
        ),
        axis=1,
    )
    instagram_detail_followers = summary["Creator Key"].map(instagram_followers).fillna(0)
    detail_followers = direct_followers.where(
        direct_followers.gt(0),
        instagram_detail_followers.where(instagram_mask, 0),
    )
    existing_followers = pd.to_numeric(summary.get("Current Followers", 0), errors="coerce").fillna(0)
    summary["Current Followers"] = existing_followers.where(
        existing_followers.gt(0),
        detail_followers,
    )

    failed = set(failed_platforms or [])
    failed_creator_keys = {
        (_text(platform), creator_key(handle))
        for platform, handle in (failed_creators or [])
    }
    summary["Profile Data Status"] = summary.apply(
        lambda row: (
            "Unavailable"
            if row["Platform"] in failed
            or (row["Platform"], row["Creator Key"]) in failed_creator_keys
            else "Available"
            if pd.notna(row.get("Profile Posts")) and float(row.get("Profile Posts") or 0) > 0
            else "No recent public posts"
        ),
        axis=1,
    )
    for column in ["Profile Posts", "Current Followers"]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0)
    no_recent_posts = summary["Profile Posts"].le(0)
    for column in [
        "Profile Average Views",
        "Profile Average Engagement",
        "Profile Average Engagement Rate",
    ]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce")
        summary.loc[no_recent_posts, column] = 0
    return summary[PROFILE_METRIC_COLUMNS]


def fetch_direct_creator_profile_metrics(
    creators,
    *,
    months: int = 3,
    post_limit: int = DEFAULT_PROFILE_POST_LIMIT,
    history_mode: str = DEFAULT_PROFILE_HISTORY_MODE,
    profile_fetcher: Optional[Callable[[str], str]] = None,
    extractor: Optional[Callable[[str, int], Dict]] = None,
    full_extractor: Optional[Callable[[str, object, object, int], Dict]] = None,
    instagram_extractor: Optional[Callable[[str, object, object, int], Dict]] = None,
    as_of=None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Fetch public profile metadata directly without media downloads.

    Each creator is isolated so a blocked, renamed, private, or malformed
    profile cannot discard successful results for the other selected creators.
    """
    requested = _requested_creator_frame(creators)
    if requested.empty:
        return pd.DataFrame(columns=PROFILE_METRIC_COLUMNS), []

    months = max(int(months), 1)
    history_mode, post_limit = profile_history_settings(history_mode, post_limit)
    fetch_profile_html = profile_fetcher or _fetch_tiktok_profile_html
    extract_user_playlist = extractor or _extract_tiktok_user_playlist
    extract_full_window = full_extractor or _extract_tiktok_user_full_window
    extract_instagram_window = instagram_extractor or _extract_instagram_user_full_window
    effective_as_of = _utc_timestamp(as_of)
    cutoff_utc = effective_as_of - pd.DateOffset(months=months)

    rows: List[Dict] = []
    errors: List[str] = []
    failed_creators: List[Tuple[str, str]] = []
    profile_followers: Dict[Tuple[str, str], int] = {}
    partial_statuses: Dict[Tuple[str, str], str] = {}
    followers_unavailable = set()

    for _, target in requested.iterrows():
        platform = _text(target.get("Platform"))
        handle = normalize_creator_handle(target.get("Profile Creator"))
        key = creator_key(handle)
        if platform == INSTAGRAM_REELS:
            try:
                extraction_result = extract_instagram_window(
                    handle,
                    cutoff_utc,
                    effective_as_of,
                    post_limit,
                )
                if not isinstance(extraction_result, dict):
                    raise RuntimeError("Instagram profile posts were not available.")
                followers = _number(extraction_result.get("followers"))
                profile_followers[(platform, key)] = followers
                if not followers:
                    followers_unavailable.add((platform, key))
                for entry in extraction_result.get("entries", []) or []:
                    if isinstance(entry, dict):
                        rows.append(_instagram_post_row(entry))
                if extraction_result.get("complete") is not True:
                    reason = _text(extraction_result.get("partial_reason"))
                    partial_statuses[(platform, key)] = (
                        f"Partial ({reason or 'full history may be incomplete'})"
                    )
            except Exception:
                failed_creators.append((platform, key))
                errors.append(
                    f"Instagram creator @{handle} could not be retrieved anonymously in this run."
                )
            continue
        if platform != TIKTOK:
            failed_creators.append((platform, key))
            errors.append(f"Creator @{handle} uses an unsupported platform.")
            continue

        try:
            profile_url = creator_profile_url(platform, handle)
            try:
                profile_html = fetch_profile_html(profile_url)
            except Exception:
                # TikTok can intermittently return an anti-bot page without
                # the public hydration data. yt-dlp can still resolve the
                # public profile URL directly, so do not turn that transient
                # HTML response into a false Unavailable result.
                profile_html = ""
            sec_uid, followers, public_post_count = _tiktok_profile_details(profile_html)
            extraction_query = f"tiktokuser:{sec_uid}" if sec_uid else profile_url
            if not sec_uid:
                followers_unavailable.add((platform, key))
            profile_followers[(platform, key)] = followers
            if public_post_count == 0:
                entries = []
                extraction_complete = True
                partial_reason = ""
            elif history_mode == PROFILE_HISTORY_FULL:
                extraction_result = extract_full_window(
                    extraction_query,
                    cutoff_utc,
                    effective_as_of,
                    post_limit,
                )
                if not isinstance(extraction_result, dict):
                    raise RuntimeError("TikTok profile posts were not available.")
                entries = [
                    entry
                    for entry in list(extraction_result.get("entries", []) or [])
                    if isinstance(entry, dict)
                ]
                extraction_complete = extraction_result.get("complete") is True
                partial_reason = _text(extraction_result.get("partial_reason"))
                if not extraction_complete and not partial_reason:
                    partial_reason = "full history may be incomplete"
                if (
                    not entries
                    and not extraction_complete
                    and "could not be read" in partial_reason.casefold()
                ):
                    raise RuntimeError("TikTok profile posts were not available.")
            else:
                playlist = extract_user_playlist(extraction_query, post_limit)
                if not isinstance(playlist, dict):
                    raise RuntimeError("TikTok profile posts were not available.")
                entries = [
                    entry
                    for entry in list(playlist.get("entries", []) or [])
                    if isinstance(entry, dict)
                ]
                if not entries:
                    raise RuntimeError("TikTok profile posts were not available.")
                extraction_complete = True
                partial_reason = ""
            seen_post_ids = set()
            accepted_entries = 0
            for entry in entries:
                post_identity = _text(
                    _first(entry, ("id", "display_id", "webpage_url", "url"))
                )
                if post_identity and post_identity in seen_post_ids:
                    continue
                if post_identity:
                    seen_post_ids.add(post_identity)
                if accepted_entries >= post_limit:
                    if history_mode == PROFILE_HISTORY_FULL:
                        cap_reason = (
                            f"{FULL_PROFILE_POST_CEILING}-post safety limit reached"
                        )
                        partial_reason = "; ".join(
                            reason
                            for reason in (partial_reason, cap_reason)
                            if reason
                        )
                        extraction_complete = False
                    break
                rows.append(
                    _yt_dlp_tiktok_post_row(
                        entry,
                        creator=handle,
                        followers=followers,
                    )
                )
                accepted_entries += 1
            if history_mode == PROFILE_HISTORY_FULL and not extraction_complete:
                partial_statuses[(platform, key)] = (
                    f"Partial ({partial_reason or 'full history may be incomplete'})"
                )
        except Exception:
            failed_creators.append((platform, key))
            errors.append(f"TikTok creator @{handle} could not be retrieved in this run.")

    metrics = _aggregate_profile_posts(
        requested,
        rows,
        profile_followers=profile_followers,
        failed_creators=failed_creators,
        months=months,
        as_of=as_of,
    )
    for (platform, key), status in partial_statuses.items():
        mask = metrics["Platform"].eq(platform) & metrics["Creator Key"].eq(key)
        mask &= metrics["Profile Data Status"].ne("Unavailable")
        metrics.loc[mask, "Profile Data Status"] = status
    for platform, key in followers_unavailable:
        mask = metrics["Platform"].eq(platform) & metrics["Creator Key"].eq(key)
        mask &= ~metrics["Profile Data Status"].isin(["Unavailable"])
        mask &= ~metrics["Profile Data Status"].astype(str).str.startswith("Partial")
        has_posts = pd.to_numeric(
            metrics["Profile Posts"], errors="coerce"
        ).fillna(0).gt(0)
        metrics.loc[mask & has_posts, "Profile Data Status"] = (
            "Available (followers unavailable)"
        )
        metrics.loc[mask & ~has_posts, "Profile Data Status"] = (
            "No recent public posts (followers unavailable)"
        )
    instagram_public = (
        metrics["Platform"].eq(INSTAGRAM_REELS)
        & metrics["Profile Data Status"].eq("Available")
    )
    metrics.loc[instagram_public, "Profile Data Status"] = (
        "Available (public metrics; shares/saves unavailable)"
    )
    return metrics, errors


def reconcile_creator_profile_fallback_metrics(
    direct_metrics: pd.DataFrame,
    fallback_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Keep free profile data unless the paid fallback is genuinely better."""
    direct = (
        direct_metrics.copy()
        if isinstance(direct_metrics, pd.DataFrame)
        else pd.DataFrame()
    )
    fallback = (
        fallback_metrics.copy()
        if isinstance(fallback_metrics, pd.DataFrame)
        else pd.DataFrame()
    )
    if direct.empty:
        return fallback.reset_index(drop=True)
    if fallback.empty:
        return direct.reset_index(drop=True)

    columns = list(dict.fromkeys([*direct.columns, *fallback.columns]))

    def row_key(row: Dict) -> Tuple[str, str]:
        return _text(row.get("Platform")), creator_key(row.get("Creator Key"))

    def numeric_value(row: Dict, column: str):
        return pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]

    direct_rows = {row_key(row): row for row in direct.to_dict("records")}
    fallback_rows = {row_key(row): row for row in fallback.to_dict("records")}
    ordered_keys = list(dict.fromkeys([*direct_rows, *fallback_rows]))
    selected_rows = []

    for key in ordered_keys:
        direct_row = direct_rows.get(key)
        fallback_row = fallback_rows.get(key)
        if direct_row is None:
            selected_rows.append(fallback_row)
            continue
        if fallback_row is None:
            selected_rows.append(direct_row)
            continue

        direct_status = _text(direct_row.get("Profile Data Status"))
        fallback_status = _text(fallback_row.get("Profile Data Status"))
        direct_unavailable = (
            not direct_status or direct_status.casefold().startswith("unavailable")
        )
        fallback_unavailable = (
            not fallback_status or fallback_status.casefold().startswith("unavailable")
        )
        direct_posts = numeric_value(direct_row, "Profile Posts")
        fallback_posts = numeric_value(fallback_row, "Profile Posts")
        direct_views = numeric_value(direct_row, "Profile Average Views")
        fallback_views = numeric_value(fallback_row, "Profile Average Views")
        direct_views_missing = (
            pd.notna(direct_posts) and direct_posts > 0 and pd.isna(direct_views)
        )
        fallback_improves_views = (
            pd.notna(fallback_posts)
            and fallback_posts > 0
            and pd.notna(fallback_views)
        )
        use_fallback = (
            not fallback_unavailable
            and (direct_unavailable or (direct_views_missing and fallback_improves_views))
        )
        selected = dict(fallback_row if use_fallback else direct_row)

        selected_status = _text(selected.get("Profile Data Status"))
        selected_posts = numeric_value(selected, "Profile Posts")
        selected_views = numeric_value(selected, "Profile Average Views")
        if use_fallback and selected_status.casefold().startswith("available"):
            if pd.notna(selected_posts) and selected_posts > 0 and pd.isna(selected_views):
                selected["Profile Data Status"] = (
                    "Available (Apify fallback: latest 20 posts; views unavailable)"
                )
            else:
                selected["Profile Data Status"] = (
                    "Available (Apify fallback: latest 20 posts)"
                )
        elif (
            not use_fallback
            and direct_views_missing
            and selected_status.casefold().startswith("available")
        ):
            selected["Profile Data Status"] = (
                "Available (views unavailable after Apify fallback)"
            )
        selected_rows.append(selected)

    return pd.DataFrame(selected_rows).reindex(columns=columns).reset_index(drop=True)


def instagram_profile_requires_fallback(metrics: pd.DataFrame) -> bool:
    """Return True when direct Instagram results are missing essential fields."""
    if not isinstance(metrics, pd.DataFrame) or metrics.empty:
        return True
    required = {"Platform", "Profile Data Status", "Current Followers"}
    if not required.issubset(metrics.columns):
        return True
    instagram = metrics[metrics.get("Platform", pd.Series(dtype=str)).eq(INSTAGRAM_REELS)]
    if instagram.empty:
        return True
    status = instagram.get(
        "Profile Data Status", pd.Series("", index=instagram.index, dtype=str)
    ).fillna("").astype(str)
    followers = pd.to_numeric(
        instagram.get("Current Followers", 0), errors="coerce"
    ).fillna(0)
    incomplete_status = status.str.startswith(("Unavailable", "Partial"))
    followers_missing = followers.le(0)
    views_missing = pd.Series(False, index=instagram.index)
    if {"Profile Posts", "Profile Average Views"}.issubset(instagram.columns):
        posts = pd.to_numeric(instagram["Profile Posts"], errors="coerce").fillna(0)
        views = pd.to_numeric(instagram["Profile Average Views"], errors="coerce")
        views_missing = posts.gt(0) & views.isna()
    return bool((incomplete_status | followers_missing | views_missing).any())


def tiktok_profile_requires_fallback(metrics: pd.DataFrame) -> bool:
    """Return True when direct TikTok profile results need paid recovery."""
    if not isinstance(metrics, pd.DataFrame) or metrics.empty:
        return True
    required = {"Platform", "Profile Data Status", "Current Followers"}
    if not required.issubset(metrics.columns):
        return True
    tiktok = metrics[metrics.get("Platform", pd.Series(dtype=str)).eq(TIKTOK)]
    if tiktok.empty:
        return True
    status = tiktok.get(
        "Profile Data Status", pd.Series("", index=tiktok.index, dtype=str)
    ).fillna("").astype(str)
    followers = pd.to_numeric(
        tiktok.get("Current Followers", 0), errors="coerce"
    ).fillna(0)
    return bool(status.str.startswith("Unavailable").any() or followers.le(0).any())


def scrape_creator_profile_metrics(
    creators,
    apify_token: str,
    *,
    months: int = 3,
    post_limit: int = DEFAULT_PROFILE_POST_LIMIT,
    client=None,
    as_of=None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Scrape selected public profiles and return aggregate metadata only."""
    requested = _requested_creator_frame(creators)
    if requested.empty:
        return pd.DataFrame(columns=PROFILE_METRIC_COLUMNS), []
    if not _text(apify_token) and client is None:
        raise RuntimeError("Missing Apify token.")
    if client is None:
        try:
            from apify_client import ApifyClient
        except Exception as exc:  # pragma: no cover - dependency contract
            raise RuntimeError("Missing dependency: install apify-client.") from exc
        client = ApifyClient(apify_token)

    post_limit = min(max(int(post_limit), 1), 1000)
    instagram_post_limit = min(
        post_limit,
        INSTAGRAM_APIFY_FALLBACK_POST_LIMIT,
    )
    months = max(int(months), 1)
    rows: List[Dict] = []
    errors: List[str] = []
    failed_platforms: List[str] = []
    failed_creators: List[Tuple[str, str]] = []
    instagram_followers: Dict[str, int] = {}

    tiktok_handles = requested.loc[requested["Platform"].eq(TIKTOK), "Profile Creator"].tolist()
    if tiktok_handles:
        try:
            items = _run_actor_items(client, TIKTOK_PROFILE_ACTOR_ID, {
                "profiles": tiktok_handles,
                "profileScrapeSections": ["videos"],
                "profileSorting": "latest",
                "resultsPerPage": post_limit,
                "oldestPostDateUnified": f"{months} months",
                "excludePinnedPosts": True,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
                "shouldDownloadSlideshowImages": False,
                "shouldDownloadAvatars": False,
                "shouldDownloadMusicCovers": False,
                "commentsPerPost": 0,
            })
            tiktok_rows = [_tiktok_post_row(item) for item in items]
            rows.extend(tiktok_rows)
            returned_keys = {
                _text(row.get("Creator Key")) for row in tiktok_rows
                if _text(row.get("Creator Key"))
            }
            missing_handles = [
                handle for handle in tiktok_handles
                if creator_key(handle) not in returned_keys
            ]
            failed_creators.extend((TIKTOK, handle) for handle in missing_handles)
            if missing_handles:
                errors.append(
                    "TikTok profile data was not returned for "
                    f"{len(missing_handles)} creator(s)."
                )
        except Exception:
            failed_platforms.append(TIKTOK)
            errors.append("TikTok creator profiles could not be retrieved in this run.")

    instagram_handles = requested.loc[
        requested["Platform"].eq(INSTAGRAM_REELS), "Profile Creator"
    ].tolist()
    if instagram_handles:
        profile_urls = [creator_profile_url(INSTAGRAM_REELS, handle) for handle in instagram_handles]
        try:
            items = _run_actor_items(client, INSTAGRAM_PROFILE_ACTOR_ID, {
                "directUrls": profile_urls,
                "resultsType": "posts",
                # The free direct scraper may inspect the complete three-month
                # window. Keep the paid Instagram fallback deliberately small
                # so one blocked profile cannot consume a large Apify quota.
                "resultsLimit": instagram_post_limit,
                "onlyPostsNewerThan": f"{months} months",
                "skipPinnedPosts": True,
            })
            rows.extend(_instagram_post_row(item) for item in items)
        except Exception:
            failed_platforms.append(INSTAGRAM_REELS)
            errors.append("Instagram creator posts could not be retrieved in this run.")
        try:
            details = _run_actor_items(client, INSTAGRAM_PROFILE_ACTOR_ID, {
                "directUrls": profile_urls,
                "resultsType": "details",
                "resultsLimit": 1,
                "addProfileStatistics": True,
            })
            instagram_followers = _instagram_profile_followers(details)
        except Exception:
            errors.append("Instagram follower counts could not be refreshed in this run.")

        instagram_evidence = {
            _text(row.get("Creator Key")) for row in rows
            if row.get("Platform") == INSTAGRAM_REELS
            and _text(row.get("Creator Key"))
        } | set(instagram_followers)
        missing_handles = [
            handle for handle in instagram_handles
            if creator_key(handle) not in instagram_evidence
        ]
        failed_creators.extend(
            (INSTAGRAM_REELS, handle) for handle in missing_handles
        )
        if missing_handles:
            errors.append(
                "Instagram profile data was not returned for "
                f"{len(missing_handles)} creator(s)."
            )

    return _aggregate_profile_posts(
        requested,
        rows,
        instagram_followers=instagram_followers,
        failed_platforms=failed_platforms,
        failed_creators=failed_creators,
        months=months,
        as_of=as_of,
    ), errors
