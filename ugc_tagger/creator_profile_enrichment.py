"""Optional public creator-profile enrichment for the marketing dashboard.

This module deliberately retrieves metadata only. It never requests media
downloads and never persists the Apify token or returned post media URLs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import pandas as pd

from ugc_tagger.instagram_reels_adapter import INSTAGRAM_REELS, TIKTOK


TIKTOK_PROFILE_ACTOR_ID = "clockworks/tiktok-scraper"
INSTAGRAM_PROFILE_ACTOR_ID = "apify/instagram-scraper"
DEFAULT_PROFILE_POST_LIMIT = 20
PROFILE_SCOPE_OPTIONS = ("Top 5", "Top 10", "Top 20")
DIRECT_PROFILE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

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
    views = _number(
        _first(
            record,
            ("videoPlayCount", "videoViewCount", "viewCount", "playCount", "viewsCount"),
            0,
        )
    )
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
        "Engagement Rate": (engagement / views * 100) if views else pd.NA,
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


def _tiktok_profile_details(page_html: str) -> Tuple[str, int, Optional[int]]:
    """Extract a public TikTok profile's secUid, followers, and post count."""
    source = _text(page_html)
    if not source:
        return "", 0, None

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
        sec_uid = _text(_recursive_first(payload, ("secUid", "sec_uid")))
        if sec_uid:
            followers = _number(
                _recursive_first(
                    payload,
                    ("followerCount", "followersCount", "follower_count"),
                )
            )
            post_count_value = _recursive_first(
                payload,
                ("videoCount", "postCount", "video_count", "post_count"),
            )
            post_count = (
                _number(post_count_value)
                if post_count_value not in (None, "")
                else None
            )
            return sec_uid, followers, post_count

    # TikTok occasionally moves the hydration payload while retaining these
    # public JSON fields. Keep a narrow fallback rather than storing the page.
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
        _number(follower_match.group(1) if follower_match else 0),
        _number(post_count_match.group(1)) if post_count_match else None,
    )


def _fetch_tiktok_profile_html(profile_url: str) -> str:
    """Retrieve public profile HTML without cookies, proxies, or media."""
    import requests

    response = requests.get(
        profile_url,
        headers={
            "User-Agent": DIRECT_PROFILE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.text


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
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    numeric = pd.to_numeric(values, errors="coerce")
    unix_mask = numeric.notna() & numeric.between(1_000_000_000, 99_999_999_999)
    if unix_mask.any():
        parsed.loc[unix_mask] = pd.to_datetime(
            numeric.loc[unix_mask], unit="s", errors="coerce", utc=True
        )
    return parsed


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
    for column in [
        "Profile Posts", "Current Followers", "Profile Average Views",
        "Profile Average Engagement", "Profile Average Engagement Rate",
    ]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0)
    return summary[PROFILE_METRIC_COLUMNS]


def fetch_direct_creator_profile_metrics(
    creators,
    *,
    months: int = 3,
    post_limit: int = DEFAULT_PROFILE_POST_LIMIT,
    profile_fetcher: Optional[Callable[[str], str]] = None,
    extractor: Optional[Callable[[str, int], Dict]] = None,
    as_of=None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Fetch TikTok profile metadata directly without Apify or media downloads.

    Each creator is isolated so a blocked, renamed, private, or malformed
    profile cannot discard successful results for the other selected creators.
    Instagram is deliberately reported as unavailable until a direct provider
    with the same metadata-only contract is implemented.
    """
    requested = _requested_creator_frame(creators)
    if requested.empty:
        return pd.DataFrame(columns=PROFILE_METRIC_COLUMNS), []

    months = max(int(months), 1)
    post_limit = min(
        max(int(post_limit), 1),
        DEFAULT_PROFILE_POST_LIMIT,
    )
    fetch_profile_html = profile_fetcher or _fetch_tiktok_profile_html
    extract_user_playlist = extractor or _extract_tiktok_user_playlist

    rows: List[Dict] = []
    errors: List[str] = []
    failed_creators: List[Tuple[str, str]] = []
    profile_followers: Dict[Tuple[str, str], int] = {}

    for _, target in requested.iterrows():
        platform = _text(target.get("Platform"))
        handle = normalize_creator_handle(target.get("Profile Creator"))
        key = creator_key(handle)
        if platform == INSTAGRAM_REELS:
            failed_creators.append((platform, key))
            errors.append(
                f"Instagram creator @{handle} is not supported by the direct profile scraper yet."
            )
            continue
        if platform != TIKTOK:
            failed_creators.append((platform, key))
            errors.append(f"Creator @{handle} uses an unsupported platform.")
            continue

        try:
            profile_html = fetch_profile_html(creator_profile_url(platform, handle))
            sec_uid, followers, public_post_count = _tiktok_profile_details(profile_html)
            if not sec_uid:
                raise RuntimeError("TikTok profile identifier was not available.")
            profile_followers[(platform, key)] = followers
            if public_post_count == 0:
                entries = []
            else:
                playlist = extract_user_playlist(f"tiktokuser:{sec_uid}", post_limit)
                if not isinstance(playlist, dict):
                    raise RuntimeError("TikTok profile posts were not available.")
                entries = [
                    entry
                    for entry in list(playlist.get("entries", []) or [])
                    if isinstance(entry, dict)
                ]
                if not entries:
                    raise RuntimeError("TikTok profile posts were not available.")
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
                rows.append(
                    _yt_dlp_tiktok_post_row(
                        entry,
                        creator=handle,
                        followers=followers,
                    )
                )
                accepted_entries += 1
                if accepted_entries >= post_limit:
                    break
        except Exception:
            failed_creators.append((platform, key))
            errors.append(f"TikTok creator @{handle} could not be retrieved in this run.")

    return _aggregate_profile_posts(
        requested,
        rows,
        profile_followers=profile_followers,
        failed_creators=failed_creators,
        months=months,
        as_of=as_of,
    ), errors


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
    months = max(int(months), 1)
    rows: List[Dict] = []
    errors: List[str] = []
    failed_platforms: List[str] = []
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
            rows.extend(_tiktok_post_row(item) for item in items)
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
                "resultsLimit": post_limit,
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

    return _aggregate_profile_posts(
        requested,
        rows,
        instagram_followers=instagram_followers,
        failed_platforms=failed_platforms,
        months=months,
        as_of=as_of,
    ), errors
