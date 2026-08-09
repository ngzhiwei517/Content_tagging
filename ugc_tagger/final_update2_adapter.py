"""Schema adapter between the v55 marketing UI and final_update_2 backend."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

import pandas as pd
import requests

from ugc_tagger.final_update2_backend import load_backend
from ugc_tagger.instagram_reels_adapter import (
    INSTAGRAM_REELS,
    TIKTOK,
    detect_platform,
    normalize_post_url,
    platform_for_record,
    post_identifier,
    scrape_instagram_posts_direct,
    scrape_instagram_posts,
)
from ugc_tagger.model_comparison import DEFAULT_GEMINI_MODEL, normalize_gemini_model
from ugc_tagger.drama_analysis import (
    DRAMA_EXPORT_COLUMNS,
    DRAMA_REVIEW_OPTIONS,
    build_review_drama_updates,
    drama_review_defaults,
    has_drama_label,
)
from ugc_tagger.direct_post_scraper import scrape_tiktok_posts_direct


# Keep the runtime version beside the UI/backend schema boundary.  Importing
# ``__version__`` from the package initializer caused Streamlit Cloud startup
# to fail when its hot-reload cache briefly exposed the older initializer.
# ``app.py`` imports this constant with the rest of the adapter API, so startup
# no longer depends on package metadata being refreshed first.
APP_VERSION = "v68.42.12"


ProgressCallback = Callable[[int, int, str], None]
RowResultCallback = Callable[[int, Dict, str], None]


CAMPAIGN_MARKETS = {"PH", "MY", "ID", "KR", "SG", "VN", "TH"}
CAMPAIGN_MARKET_ALIASES = {
    "PHILIPPINES": "PH",
    "PHILIPPINE": "PH",
    "MALAYSIA": "MY",
    "INDONESIA": "ID",
    "INDONESIAN": "ID",
    "IDN": "ID",
    "KOREA": "KR",
    "SOUTH KOREA": "KR",
    "SINGAPORE": "SG",
    "VIETNAM": "VN",
    "VIET NAM": "VN",
    "THAILAND": "TH",
}
CAMPAIGN_MARKET_MISSING = {
    "", "OTHER", "OTHER / NO MARKET", "OTHER/NO MARKET", "NO MARKET",
    "UNKNOWN", "NOT SPECIFIED", "N/A", "NA", "NONE", "NULL", "NAN",
}
TIKTOK_SHORT_LINK_HOSTS = {"vt.tiktok.com", "vm.tiktok.com"}
RETIRED_CREATIVE_TYPES = {"Carousel"}


MARKETING_EXPORT_COLUMNS = [
    "Platform", "Source", "Link", "Market", "Track", "Original Sound", "Campaign Artist", "Creator", "Followers", "KOL Size",
    "Views", "Likes", "Comments", "Shares", "Saves", "Metrics Unavailable", "Total Engagement",
    "Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate",
    # Detailed drama fields are deliberately consolidated into Content Details
    # so the marketing export remains one clean, readable table.
    "Narrative", "Creative Type", "Content Details",
]

QA_AUDIT_COLUMNS = [
    "Original AI Labels", "Final Labels", "Human Reviewed", "Human Edited",
    "Label History", "Verifier Status", "Verifier Model", "Verifier Fallback Used",
    "Verifier Input Labels",
    "Verifier Output Labels", "Verifier Confidence", "Verifier Reason",
    "Verifier Evidence", "Verifier Triggers",
]


# -----------------------------------------------------------------------------
# Scalar normalization and label-audit history
# -----------------------------------------------------------------------------


def _text(value) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def normalize_campaign_market(value) -> str:
    """Canonicalize user-supplied campaign market without using TikTok location."""
    raw = re.sub(r"\s+", " ", _text(value)).strip().upper()
    if raw in CAMPAIGN_MARKET_MISSING:
        return ""
    if raw in CAMPAIGN_MARKETS:
        return raw
    return CAMPAIGN_MARKET_ALIASES.get(raw, "")


def _number(value) -> int:
    try:
        if pd.isna(value):
            return 0
    except Exception:
        pass
    try:
        return int(float(str(value).replace(",", "").strip() or 0))
    except Exception:
        return 0


def _float(value) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def normalize_label_list(value) -> List[str]:
    """Return an ordered, de-duplicated label list for audit comparisons."""
    if isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = _text(value).split(",") if _text(value) else []
    labels: List[str] = []
    for item in raw:
        label = _text(item)
        if label and label not in labels:
            labels.append(label)
    return labels[:2]


def operational_creative_type(value, fallback: str = "Others") -> str:
    """Remove format-only labels from the user-facing Creative Type value."""
    labels = [
        label
        for label in normalize_label_list(value)
        if label not in RETIRED_CREATIVE_TYPES
    ]
    return ", ".join(labels[:2]) if labels else fallback


def _history_entries(value) -> List[Dict]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [dict(value)]
    text = _text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [dict(item) for item in parsed if isinstance(item, dict)]
    return []


def append_label_history(
    history,
    *,
    stage: str,
    labels,
    action: str,
    note: str = "",
    tier: str = "",
    validation_status: str = "",
    recorded_at: Optional[str] = None,
) -> str:
    """Append one JSON audit event without exposing it in marketing exports."""
    entries = _history_entries(history)
    entry = {
        "stage": _text(stage),
        "action": _text(action).upper(),
        "labels": normalize_label_list(labels),
        "recorded_at": recorded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if _text(note):
        entry["note"] = _text(note)
    if _text(tier):
        entry["tier"] = _text(tier)
    if _text(validation_status):
        entry["validation_status"] = _text(validation_status)
    entries.append(entry)
    return json.dumps(entries, ensure_ascii=False)


def initial_label_audit(
    labels,
    *,
    tier: str = "",
    validation_status: str = "",
    pre_verifier_labels="",
    verifier_status: str = "",
    verifier_note: str = "",
    verifier_confidence=0,
) -> Dict:
    automated = normalize_label_list(labels) or ["Others"]
    automated_text = ", ".join(automated)
    pre_verifier = normalize_label_list(pre_verifier_labels)
    status = _text(verifier_status).lower()
    history = ""
    if pre_verifier and status and status != "not_run":
        history = append_label_history(
            history,
            stage="automated_pre_verifier",
            labels=pre_verifier,
            action="AUTO",
            tier=tier,
            validation_status=validation_status,
        )
        note_parts = []
        try:
            confidence = float(verifier_confidence or 0)
        except (TypeError, ValueError):
            confidence = 0
        if confidence:
            note_parts.append(f"confidence={confidence:.0%}")
        if _text(verifier_note):
            note_parts.append(_text(verifier_note))
        history = append_label_history(
            history,
            stage="targeted_evidence_verifier",
            labels=automated,
            action=status,
            note="; ".join(note_parts),
            tier=tier,
            validation_status=validation_status,
        )
    else:
        history = append_label_history(
            history,
            stage="automated",
            labels=automated,
            action="AUTO",
            tier=tier,
            validation_status=validation_status,
        )
    return {
        "Original AI Labels": automated_text,
        "Final Labels": automated_text,
        "Human Reviewed": False,
        "Human Edited": False,
        "Label History": history,
    }


def review_audit_update(
    original_ai_labels,
    final_labels,
    history,
    *,
    action: str,
    note: str = "",
    recorded_at: Optional[str] = None,
) -> Dict:
    """Build the fields written when a reviewer keeps, edits, or removes a row."""
    original = normalize_label_list(original_ai_labels)
    final = normalize_label_list(final_labels) or ["Others"]
    if not original:
        # Backward-compatible fallback for rows created before the label-audit schema.
        original = list(final)
    return {
        "Original AI Labels": ", ".join(original),
        "Final Labels": ", ".join(final),
        "Human Reviewed": True,
        "Human Edited": original != final,
        "Label History": append_label_history(
            history,
            stage="human_review",
            labels=final,
            action=action,
            note=note,
            validation_status="removed" if _text(action).upper() == "REMOVE" else "reviewed",
            recorded_at=recorded_at,
        ),
    }


# -----------------------------------------------------------------------------
# Post identity and scraped-record matching
# -----------------------------------------------------------------------------


def video_id(url: str) -> str:
    match = re.search(r"/(?:video|photo)/(\d+)", _text(url))
    return match.group(1) if match else ""


def normalize_url(url: str) -> str:
    return normalize_post_url(_text(url))


def is_tiktok_short_url(url: str) -> bool:
    """Return whether *url* is a TikTok redirect-style share link."""
    try:
        host = (urlsplit(_text(url)).hostname or "").lower()
    except ValueError:
        return False
    return host in TIKTOK_SHORT_LINK_HOSTS


def resolve_tiktok_short_url(url: str, timeout_seconds: int = 10) -> str:
    """Resolve a TikTok ``vt``/``vm`` share link to a stable post URL.

    Only TikTok-owned short-link hosts are contacted. If TikTok blocks the
    redirect request or the resolved location is not a recognisable TikTok
    post URL, the original link is returned so Apify still gets a chance to
    process it.
    """
    original = _text(url)
    if not is_tiktok_short_url(original):
        return original

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        )
    }
    resolved = ""
    response = None
    try:
        response = requests.head(
            original,
            headers=headers,
            allow_redirects=True,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        resolved = _text(response.url)
    except requests.RequestException:
        if response is not None:
            getattr(response, "close", lambda: None)()
        response = None
        try:
            response = requests.get(
                original,
                headers=headers,
                allow_redirects=True,
                stream=True,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            resolved = _text(response.url)
        except requests.RequestException:
            return original
        finally:
            if response is not None:
                getattr(response, "close", lambda: None)()
    else:
        getattr(response, "close", lambda: None)()

    if detect_platform(resolved) == TIKTOK and post_identifier(resolved):
        return normalize_url(resolved)
    return original


def record_urls(record: Dict) -> List[str]:
    """Return every usable URL alias carried by an Apify record."""
    urls: List[str] = []
    for key in (
        "webVideoUrl",
        "submittedVideoUrl",
        "url",
        "inputUrl",
        "itemWebUrl",
        "shareUrl",
        "postUrl",
        "_requested_url",
        "_resolved_url",
    ):
        value = _text(record.get(key))
        if value and value not in urls:
            urls.append(value)
    video_meta = record.get("videoMeta") if isinstance(record.get("videoMeta"), dict) else {}
    nested_url = _text(video_meta.get("webVideoUrl"))
    if nested_url and nested_url not in urls:
        urls.append(nested_url)
    return urls


def record_url(record: Dict) -> str:
    urls = record_urls(record)
    return urls[0] if urls else ""


def index_records(records: Iterable[Dict]) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    by_id: Dict[str, Dict] = {}
    by_url: Dict[str, Dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_id = _text(record.get("id"))
        if raw_id:
            by_id[raw_id] = record
        for url in record_urls(record):
            for post_id in (post_identifier(url), video_id(url)):
                if post_id:
                    by_id[post_id] = record
            by_url[normalize_url(url)] = record
    return by_id, by_url


def match_record(row, by_id: Dict[str, Dict], by_url: Dict[str, Dict]) -> Optional[Dict]:
    link = _text(row.get("Link"))
    stable_id = post_identifier(link)
    legacy_tiktok_id = video_id(link)
    return (
        by_id.get(stable_id)
        or by_id.get(legacy_tiktok_id)
        or by_url.get(normalize_url(link))
    )


def review_cache(records: Iterable[Dict]) -> Dict[str, Dict]:
    cache: Dict[str, Dict] = {}
    by_id, by_url = index_records(records)
    cache.update({f"id:{key}": value for key, value in by_id.items()})
    cache.update({f"url:{key}": value for key, value in by_url.items()})
    return cache


# -----------------------------------------------------------------------------
# Canonical backend records to current UI rows
# -----------------------------------------------------------------------------


def _creator_followers(record: Dict) -> int:
    author = record.get("authorMeta") if isinstance(record.get("authorMeta"), dict) else {}
    return _number(author.get("fans") or author.get("followers") or author.get("followerCount"))


def _creator_handle_from_post_url(url: str) -> str:
    match = re.search(r"tiktok\.com/@([^/?#]+)", _text(url), flags=re.IGNORECASE)
    return match.group(1).strip().lstrip("@") if match else ""


def _resolved_creator_handle(original: Dict, tagged: Dict) -> str:
    """Prefer a public username and never display TikTok's numeric account ID."""
    link_handle = _creator_handle_from_post_url(
        tagged.get("tiktok_url") or original.get("Link")
    )
    for value in (
        tagged.get("creator_handle"),
        tagged.get("creator"),
        original.get("Creator"),
        link_handle,
    ):
        candidate = _text(value).lstrip("@")
        if candidate and not candidate.isdigit() and candidate not in {"—", "-"}:
            return candidate
    return link_handle


def _record_music_name(record: Dict) -> str:
    """Return TikTok's scraped sound title without requiring user input."""
    music = record.get("musicMeta") if isinstance(record.get("musicMeta"), dict) else {}
    return _text(
        music.get("musicName")
        or record.get("musicName")
        or record.get("musicTitle")
        or record.get("soundName")
    )


def _resolved_campaign_track(row, record: Dict) -> str:
    """Prefer an uploaded track; otherwise use the scraped TikTok sound title."""
    track = _text(row.get("Track"))
    artist = _text(row.get("Campaign Artist"))
    if track and artist and " - " not in track:
        return f"{artist} - {track}"
    return track or _record_music_name(record)


_NARRATIVE_PLACEHOLDERS = {
    "", "na", "n/a", "none", "null", "unknown", "not available",
    "not specified", "?",
}


def _narrative_values(value) -> List[str]:
    """Return stable text values from a scalar or list-like backend field."""
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = re.split(r"\s*[,|]\s*", _text(value)) if _text(value) else []
    return [text for item in items if (text := _text(item))]


def _resolved_narrative_suggestion(tagged: Dict, creative_type: str) -> str:
    """Keep a real AI narrative and replace only placeholder/failed values.

    The legacy backend deliberately permits ``NA``.  That is safe for storage
    but unhelpful on the marketing review screen.  This fallback stays
    evidence-bound: it summarizes the already selected detailed category or
    broad creative label and never invents a new label from a TikTok URL.
    """
    existing = _text(tagged.get("Narrative") or tagged.get("narrative"))
    if existing.casefold().strip(". ") not in _NARRATIVE_PLACEHOLDERS:
        return existing

    issues = " ".join([
        _text(tagged.get("validation_issues")),
        _text(tagged.get("tier3_reason")),
        _text(tagged.get("reasoning")),
    ]).casefold()
    if _truthy(tagged.get("parse_error")) or "parse error" in issues:
        return "Content needs review"

    categories = _narrative_values(
        tagged.get("Drama Content Category")
        or tagged.get("content_categories")
        or tagged.get("content_kind")
    )
    category = categories[0] if categories else ""
    edit_focus = _text(tagged.get("Drama Edit Focus") or tagged.get("edit_focus"))
    drama_type = _text(tagged.get("Drama Type") or tagged.get("drama_type"))

    if category == "CP Edit":
        return {
            "BL CP Edit": "BL actor chemistry",
            "GL CP Edit": "GL actor chemistry",
        }.get(edit_focus, "Actor couple chemistry")
    if category == "Drama Edit":
        return {
            "BL Drama": "BL drama moments",
            "GL Drama": "GL drama moments",
        }.get(drama_type, "Drama story moments")

    category_narratives = {
        "Entertainment News": "Entertainment news",
        "Anime Edit": "Anime story moments",
        "Actor/Actress Carousel": "Actor/actress profile",
        "Drama Carousel": "Drama story highlights",
        "Behind-the-Scenes Edit": "Behind-the-scenes moments",
        "K-pop Show Cut": "K-pop show moments",
        "Actor/Actress Daily Vlog": "Actor/actress daily life",
        "POV": "Point-of-view story",
        "Other": "Other content",
    }
    if category in category_narratives:
        return category_narratives[category]

    broad_narratives = {
        "Comedy": "Humorous moment",
        "Dance": "Dance performance",
        "Lip Sync": "Lip-sync performance",
        "Fashion": "Fashion showcase",
        "Beauty": "Beauty showcase",
        "Fitness": "Fitness content",
        "Travel": "Travel moment",
        "Relationship": "Relationship moment",
        "Reflection": "Personal reflection",
        "Quotes": "Text-led message",
        "Gaming": "Gaming content",
        "Movie/Tv/Drama Edits": "Drama or entertainment edit",
        "Celebrity Edits": "Celebrity edit",
        "Slice of Life": "Everyday life moment",
        "Lyrics": "Lyrics-focused post",
        "Lyrics Translation": "Translated lyrics post",
        "Media/Infotainment": "Informational content",
        "Others": "Other content",
    }
    for label in _narrative_values(creative_type):
        if label in broad_narratives:
            return broad_narratives[label]
    return "Content needs review"


def _to_ui_row(original, tagged, raw_record: Dict) -> Dict:
    original_dict = original.to_dict() if hasattr(original, "to_dict") else dict(original)
    tagged_dict = tagged.to_dict() if hasattr(tagged, "to_dict") else dict(tagged)
    output = dict(original_dict)

    review_action = _text(tagged_dict.get("review_action")).upper()
    validation_status = _text(tagged_dict.get("validation_status"))
    removed = review_action == "REMOVE" or validation_status.lower() == "removed"
    if removed:
        validation_status = "removed"
    needs_review = False if removed else _truthy(tagged_dict.get("needs_human_review"))
    creative_type = operational_creative_type(tagged_dict.get("Creative Type"))
    narrative = _resolved_narrative_suggestion(tagged_dict, creative_type)
    qa_reason = " | ".join(
        value for value in [
            _text(tagged_dict.get("validation_issues")),
            _text(tagged_dict.get("tier3_reason")),
            _text(tagged_dict.get("remove_reason")),
        ] if value
    )

    campaign_market = normalize_campaign_market(original_dict.get("Market"))
    platform = (
        _text(original_dict.get("Platform"))
        or _text(tagged_dict.get("platform"))
        or platform_for_record(raw_record, _text(original_dict.get("Link")))
        or TIKTOK
    )
    music_name = _text(tagged_dict.get("music_name")) or _record_music_name(raw_record)
    music_author = _text(tagged_dict.get("music_author"))
    unavailable_metrics = raw_record.get("instagramMetricsUnavailable", [])
    if not isinstance(unavailable_metrics, list):
        unavailable_metrics = []
    output.update({
        "App Version": APP_VERSION,
        "Platform": platform,
        "Link": _text(tagged_dict.get("tiktok_url")) or _text(original_dict.get("Link")),
        # Campaign Market is user-provided business context. Do not fall back to
        # TikTok/Apify locationCreated, which describes post or creator origin.
        "Market": campaign_market,
        "Market Source": "Uploaded file / user input" if campaign_market else "Not provided",
        "Track": (
            _text(original_dict.get("Track"))
            or _text(tagged_dict.get("track"))
            or music_name
        ),
        "Original Sound": _text(original_dict.get("Original Sound")) or music_name,
        "Source": _text(original_dict.get("Source")) or _text(tagged_dict.get("source_file")),
        "Creator": _resolved_creator_handle(original_dict, tagged_dict),
        "Creator Display": _text(tagged_dict.get("creator_display")),
        "Caption": _text(tagged_dict.get("caption")) or _text(original_dict.get("Caption")),
        "Followers": _creator_followers(raw_record) or _number(original_dict.get("Followers")),
        "Views": _number(tagged_dict.get("plays")),
        "Likes": _number(tagged_dict.get("likes")),
        "Comments": _number(tagged_dict.get("comments")),
        "Shares": _number(tagged_dict.get("shares")),
        "Saves": _number(tagged_dict.get("saves")),
        "Audio From Platform": music_name,
        "Audio Artist From Platform": music_author,
        "Track From TikTok": music_name if platform == TIKTOK else "",
        "Artist From TikTok": music_author if platform == TIKTOK else "",
        "Metrics Unavailable": ", ".join(_text(name) for name in unavailable_metrics if _text(name)),
        "Is Slideshow": _truthy(tagged_dict.get("is_slideshow")),
        "Cover URL": _text(tagged_dict.get("cover_url")),
        "Video URL": _text(tagged_dict.get("video_url")),
        "Narrative": narrative,
        "Creative Type": creative_type,
        "Content Details": _text(tagged_dict.get("Content Details")),
        "Confidence": _float(tagged_dict.get("confidence")),
        "Reasoning": _text(tagged_dict.get("reasoning")),
        "Needs Review": needs_review,
        "Review Note": qa_reason,
        "Review Action": "REMOVE" if removed else review_action,
        "QA Priority": "Removed" if removed else ("High" if needs_review else "Low"),
        "QA Reason": qa_reason,
        "Review Risk": _text(tagged_dict.get("review_risk_reasons")),
        "Tier Used": _text(tagged_dict.get("tier_used")),
        "Validation Status": validation_status,
        "Validation Score": tagged_dict.get("validation_score", 0),
        "Verifier Status": _text(tagged_dict.get("verifier_status")) or "not_run",
        "Verifier Model": _text(tagged_dict.get("verifier_model")),
        "Verifier Fallback Used": _truthy(tagged_dict.get("verifier_fallback_used")),
        "Verifier Input Labels": _text(tagged_dict.get("verifier_input_labels")),
        "Verifier Output Labels": _text(tagged_dict.get("verifier_output_labels")),
        "Verifier Confidence": _float(tagged_dict.get("verifier_confidence")),
        "Verifier Reason": _text(tagged_dict.get("verifier_reason")),
        "Verifier Evidence": _text(tagged_dict.get("verifier_evidence")),
        "Verifier Triggers": _text(tagged_dict.get("verifier_triggers")),
        "Manual Metrics Required": _truthy(tagged_dict.get("manual_metrics_required")),
        "Raw Apify Status": _text(raw_record.get("error")) or _text(raw_record.get("errorCode")) or "OK",
        "_raw_row_json": _text(tagged_dict.get("_raw_row_json")),
    })
    for column in DRAMA_EXPORT_COLUMNS:
        output[column] = _text(tagged_dict.get(column))
    output.update(initial_label_audit(
        creative_type,
        tier=_text(tagged_dict.get("tier_used")),
        validation_status=validation_status,
        pre_verifier_labels=tagged_dict.get("verifier_input_labels", ""),
        verifier_status=tagged_dict.get("verifier_status", ""),
        verifier_note=tagged_dict.get("verifier_reason", ""),
        verifier_confidence=tagged_dict.get("verifier_confidence", 0),
    ))
    output["Total Engagement"] = sum(output.get(key, 0) for key in ["Likes", "Comments", "Shares", "Saves"])
    return output


def failed_analysis_review_row(original, *, platform: str = "") -> Dict:
    """Build a safe manual-review row after one post-specific runtime failure.

    The raw exception is deliberately not stored. Reviewers still receive the
    original link and campaign context, and can open the post to finish tagging.
    """
    original_dict = original.to_dict() if hasattr(original, "to_dict") else dict(original)
    link = _text(original_dict.get("Link"))
    resolved_platform = (
        _text(platform)
        or _text(original_dict.get("Platform"))
        or detect_platform(link)
        or TIKTOK
    )
    raw_record = {
        "url": link,
        "submittedVideoUrl": link,
        "_platform": resolved_platform,
        "platform": resolved_platform,
    }
    output = _to_ui_row(
        original_dict,
        {
            "Creative Type": "Others",
            "Content Details": (
                "Automated analysis could not finish for this post. "
                "Open the original post and confirm the tags manually."
            ),
            "confidence": 0,
            "needs_human_review": True,
            "review_action": "",
            "review_risk_reasons": "Post-specific analysis interruption",
            "tier_used": "runtime_manual_review",
            "validation_status": "review",
            "validation_score": 0,
            "validation_issues": (
                "Automated analysis could not finish for this post; "
                "manual confirmation is required."
            ),
        },
        raw_record,
    )
    output["Gemini Called"] = True
    return output


def enrich_review_drama(
    review_row,
    raw_record: Dict,
    gemini_key: str,
    apify_token: str = "",
    logs: Optional[List[str]] = None,
) -> Dict:
    """Run the same conditional enrichment for a human-corrected drama row."""
    row_dict = review_row.to_dict() if hasattr(review_row, "to_dict") else dict(review_row)
    if not has_drama_label(row_dict.get("Final Labels") or row_dict.get("Creative Type")):
        return {}
    backend = load_backend()
    return dict(backend.enrich_existing_drama_review(
        row_dict,
        raw_record or {},
        gemini_key,
        apify_token,
        log_list=logs if logs is not None else [],
    ))


# -----------------------------------------------------------------------------
# Public adapter API used by app.py
# -----------------------------------------------------------------------------


MAX_APIFY_POSTS_PER_REQUEST = 25


def _known_instagram_view(
    known_instagram_views: Optional[Dict[str, int]],
    link: str,
) -> Optional[int]:
    """Return an explicitly supplied file view count for one Instagram URL."""
    if not known_instagram_views:
        return None
    normalized = normalize_post_url(link)
    identifier = post_identifier(link)
    for key in (normalized, link, identifier):
        if key and key in known_instagram_views:
            return _number(known_instagram_views[key])
    return None


def _apply_known_instagram_view(record: Dict, views: int) -> Dict:
    """Fill one direct record from uploaded metrics without changing its media."""
    record["playCount"] = _number(views)
    unavailable = record.get("instagramMetricsUnavailable", [])
    if not isinstance(unavailable, list):
        unavailable = []
    record["instagramMetricsUnavailable"] = [
        metric for metric in unavailable if _text(metric).casefold() != "views"
    ]
    record["_views_source"] = "uploaded_file"
    return record


def scrape_links(
    links: List[str],
    apify_token: str,
    *,
    known_instagram_views: Optional[Dict[str, int]] = None,
) -> List[Dict]:
    """Use direct retrieval first and avoid repeating uploaded IG view metrics."""
    tiktok_links = [link for link in links if detect_platform(link) == TIKTOK]
    instagram_links = [link for link in links if detect_platform(link) == INSTAGRAM_REELS]
    if len(tiktok_links) > MAX_APIFY_POSTS_PER_REQUEST:
        raise ValueError(
            "APIFY_BATCH_LIMIT_EXCEEDED: TikTok requests must contain at most "
            f"{MAX_APIFY_POSTS_PER_REQUEST} posts."
        )
    if len(instagram_links) > MAX_APIFY_POSTS_PER_REQUEST:
        raise ValueError(
            "APIFY_BATCH_LIMIT_EXCEEDED: Instagram requests must contain at most "
            f"{MAX_APIFY_POSTS_PER_REQUEST} posts."
        )
    backend = load_backend()
    records: List[Dict] = []
    if tiktok_links:
        short_link_count = sum(is_tiktok_short_url(link) for link in tiktok_links)
        if short_link_count > 1:
            worker_count = min(short_link_count, 8)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                resolved_links = list(executor.map(resolve_tiktok_short_url, tiktok_links))
        else:
            resolved_links = [resolve_tiktok_short_url(link) for link in tiktok_links]
        tiktok_requests = list(zip(tiktok_links, resolved_links))
        actor_links = [resolved for _, resolved in tiktok_requests]
        direct_records, fallback_links = scrape_tiktok_posts_direct(actor_links)
        tiktok_records = list(direct_records)
        if fallback_links:
            tiktok_records.extend(
                backend.run_apify_tiktok_scraper_api(fallback_links, apify_token)
            )
        for record in tiktok_records:
            if isinstance(record, dict):
                record.setdefault("_platform", TIKTOK)
                record.setdefault("platform", TIKTOK)

        # Attach the submitted short URL as an alias to the matching canonical
        # actor result. This keeps display/audit data unchanged while allowing
        # tag_candidates() to match the original row reliably.
        by_id, by_url = index_records(tiktok_records)
        same_length = len(tiktok_records) == len(tiktok_requests)
        for position, (original, resolved) in enumerate(tiktok_requests):
            record = match_record({"Link": resolved}, by_id, by_url)
            if not isinstance(record, dict):
                record = match_record({"Link": original}, by_id, by_url)
            if not isinstance(record, dict) and same_length:
                candidate = tiktok_records[position]
                record = candidate if isinstance(candidate, dict) else None
            if isinstance(record, dict):
                record.setdefault("_requested_url", original)
                record.setdefault("_resolved_url", resolved)
        records.extend(tiktok_records)
    if instagram_links:
        direct_records, fallback_links = scrape_instagram_posts_direct(instagram_links)
        direct_by_id, direct_by_url = index_records(direct_records)
        paid_fallback_links: List[str] = []
        for link in fallback_links:
            direct_record = match_record({"Link": link}, direct_by_id, direct_by_url)
            known_views = _known_instagram_view(known_instagram_views, link)
            if isinstance(direct_record, dict) and known_views is not None:
                _apply_known_instagram_view(direct_record, known_views)
            else:
                # A missing direct record still needs Apify for usable post/media
                # data. A partial record needs it only when uploaded Views are
                # unavailable too.
                paid_fallback_links.append(link)

        fallback_records: List[Dict] = []
        if paid_fallback_links:
            try:
                fallback_records = scrape_instagram_posts(
                    paid_fallback_links,
                    apify_token,
                )
            except Exception:
                fully_missing = [
                    link
                    for link in paid_fallback_links
                    if not isinstance(
                        match_record({"Link": link}, direct_by_id, direct_by_url),
                        dict,
                    )
                ]
                if fully_missing:
                    raise

        fallback_by_id, fallback_by_url = index_records(fallback_records)
        instagram_records: List[Dict] = []
        for link in instagram_links:
            direct_record = match_record({"Link": link}, direct_by_id, direct_by_url)
            fallback_record = match_record({"Link": link}, fallback_by_id, fallback_by_url)
            fallback_unavailable = {
                _text(metric).casefold()
                for metric in (
                    fallback_record.get("instagramMetricsUnavailable", [])
                    if isinstance(fallback_record, dict)
                    else []
                )
            }
            fallback_has_views = (
                isinstance(fallback_record, dict)
                and not _text(fallback_record.get("error") or fallback_record.get("errorCode"))
                and "views" not in fallback_unavailable
            )
            selected = (
                fallback_record
                if fallback_has_views
                else direct_record
                if isinstance(direct_record, dict)
                else fallback_record
            )
            if isinstance(selected, dict):
                instagram_records.append(selected)
        records.extend(instagram_records)
    return records


def tag_candidates(
    candidates: pd.DataFrame,
    records: List[Dict],
    gemini_key: str,
    apify_token: str,
    logs: Optional[List[str]] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_result: Optional[RowResultCallback] = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
) -> pd.DataFrame:
    """Run final_update_2 by source/market/track and return the current UI schema."""
    if candidates.empty:
        return pd.DataFrame()
    backend = load_backend()
    selected_model = normalize_gemini_model(gemini_model)
    logs = logs if logs is not None else []
    by_id, by_url = index_records(records)

    groups: OrderedDict[Tuple[str, str, str], List[Tuple[int, object, Dict]]] = OrderedDict()
    for input_position, (_, row) in enumerate(candidates.iterrows()):
        record = match_record(row, by_id, by_url)
        if not isinstance(record, dict):
            link = _text(row.get("Link"))
            platform = _text(row.get("Platform")) or detect_platform(link) or TIKTOK
            record = {
                "url": link,
                "submittedVideoUrl": link,
                "_platform": platform,
                "platform": platform,
                "error": "POST_NOT_FOUND",
                "errorCode": "POST_NOT_FOUND",
            }
        resolved_track = _resolved_campaign_track(row, record)
        campaign_market = normalize_campaign_market(row.get("Market"))
        key = (_text(row.get("Source")), campaign_market, resolved_track)
        groups.setdefault(key, []).append((input_position, row, record))

    converted: List[Tuple[int, Dict]] = []
    completed = 0
    total = len(candidates)
    # One context spans every source/market/track group in the run. Besides
    # isolating the model selection, this preserves Pro request pacing across
    # group boundaries instead of resetting the rate limiter for each group.
    with backend.gemini_model_context(selected_model):
        for (source, market, track), pairs in groups.items():
            group_records = [record for _, _, record in pairs]

            def row_done(_done, _group_total, output, tier):
                nonlocal completed
                pair_position = int(_done) - 1
                if on_result and 0 <= pair_position < len(pairs):
                    input_position, original, raw_record = pairs[pair_position]
                    converted_row = _to_ui_row(original, output, raw_record)
                    converted_row["Gemini Model"] = selected_model
                    converted_row["Gemini Called"] = _text(tier).lower() not in {
                        "auto_removed_unavailable",
                        "sensitive_human_review",
                    }
                    on_result(input_position, converted_row, _text(tier))
                completed += 1
                if on_progress:
                    on_progress(completed, total, _text(tier))

            tagged_group = backend.run_pipeline(
                group_records,
                track,
                gemini_key,
                apify_token,
                logs,
                delay_seconds=0,
                on_row_done=row_done,
                source_file=source,
                # A non-market sentinel prevents the legacy pipeline from falling
                # back to TikTok locationCreated when campaign Market is missing.
                campaign_market=market or "UNKNOWN",
            )
            tagged_rows = [row for _, row in tagged_group.iterrows()]
            for position, (input_position, original, raw_record) in enumerate(pairs):
                if position < len(tagged_rows):
                    converted.append((input_position, _to_ui_row(original, tagged_rows[position], raw_record)))
                else:
                    missing_row = _to_ui_row(original, {
                        "Creative Type": "",
                        "confidence": 0,
                        "needs_human_review": True,
                        "validation_status": "review",
                        "validation_issues": "Backend returned no output row.",
                    }, raw_record)
                    missing_row["Gemini Model"] = selected_model
                    missing_row["Gemini Called"] = True
                    converted.append((input_position, missing_row))
                    if on_result:
                        on_result(input_position, missing_row, "missing_output")
                    completed += 1
                    if on_progress:
                        on_progress(completed, total, "missing_output")

    # Source/market/track grouping is an implementation detail. Restore the
    # exact upload/paste sequence before handing rows back to the UI.
    converted.sort(key=lambda item: item[0])
    output = pd.DataFrame([row for _, row in converted]).reset_index(drop=True)
    output["Gemini Model"] = selected_model
    tier_used = output.get("Tier Used", pd.Series("", index=output.index)).fillna("").astype(str).str.lower()
    output["Gemini Called"] = ~tier_used.isin({"auto_removed_unavailable", "sensitive_human_review"})
    return output
