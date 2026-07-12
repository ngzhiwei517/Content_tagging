"""Schema adapter between the v55 marketing UI and final_update_2 backend."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from final_update2_backend import load_backend


ProgressCallback = Callable[[int, int, str], None]


MARKETING_EXPORT_COLUMNS = [
    "Source", "Link", "Market", "Track", "Creator", "Followers", "KOL Size",
    "Views", "Likes", "Comments", "Shares", "Saves", "Total Engagement",
    "Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate",
    "Narrative", "Creative Type", "Content Details",
]

QA_AUDIT_COLUMNS = [
    "Original AI Labels", "Final Labels", "Human Reviewed", "Human Edited",
    "Label History",
]


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


def initial_label_audit(labels, *, tier: str = "", validation_status: str = "") -> Dict:
    automated = normalize_label_list(labels) or ["Others"]
    automated_text = ", ".join(automated)
    return {
        "Original AI Labels": automated_text,
        "Final Labels": automated_text,
        "Human Reviewed": False,
        "Human Edited": False,
        "Label History": append_label_history(
            "",
            stage="automated",
            labels=automated,
            action="AUTO",
            tier=tier,
            validation_status=validation_status,
        ),
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


def video_id(url: str) -> str:
    match = re.search(r"/(?:video|photo)/(\d+)", _text(url))
    return match.group(1) if match else ""


def normalize_url(url: str) -> str:
    return _text(url).split("?")[0].rstrip("/").lower()


def record_url(record: Dict) -> str:
    for key in ("webVideoUrl", "submittedVideoUrl", "url", "inputUrl"):
        value = _text(record.get(key))
        if value:
            return value
    video_meta = record.get("videoMeta") if isinstance(record.get("videoMeta"), dict) else {}
    return _text(video_meta.get("webVideoUrl"))


def index_records(records: Iterable[Dict]) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    by_id: Dict[str, Dict] = {}
    by_url: Dict[str, Dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        url = record_url(record)
        post_id = _text(record.get("id")) or video_id(url)
        if post_id:
            by_id[post_id] = record
        if url:
            by_url[normalize_url(url)] = record
    return by_id, by_url


def match_record(row, by_id: Dict[str, Dict], by_url: Dict[str, Dict]) -> Optional[Dict]:
    link = _text(row.get("Link"))
    post_id = video_id(link)
    return by_id.get(post_id) if post_id else by_url.get(normalize_url(link))


def review_cache(records: Iterable[Dict]) -> Dict[str, Dict]:
    cache: Dict[str, Dict] = {}
    by_id, by_url = index_records(records)
    cache.update({f"id:{key}": value for key, value in by_id.items()})
    cache.update({f"url:{key}": value for key, value in by_url.items()})
    return cache


def _creator_followers(record: Dict) -> int:
    author = record.get("authorMeta") if isinstance(record.get("authorMeta"), dict) else {}
    return _number(author.get("fans") or author.get("followers") or author.get("followerCount"))


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
    creative_type = _text(tagged_dict.get("Creative Type")) or "Others"
    qa_reason = " | ".join(
        value for value in [
            _text(tagged_dict.get("validation_issues")),
            _text(tagged_dict.get("tier3_reason")),
            _text(tagged_dict.get("remove_reason")),
        ] if value
    )

    output.update({
        "App Version": "v68.9",
        "Link": _text(tagged_dict.get("tiktok_url")) or _text(original_dict.get("Link")),
        # Campaign Market is user-provided business context. Do not fall back to
        # TikTok/Apify locationCreated, which describes post or creator origin.
        "Market": _text(original_dict.get("Market")),
        "Market Source": "Uploaded file / user input" if _text(original_dict.get("Market")) else "Not provided",
        "Track": _text(original_dict.get("Track")) or _text(tagged_dict.get("track")),
        "Source": _text(original_dict.get("Source")) or _text(tagged_dict.get("source_file")),
        "Creator": _text(tagged_dict.get("creator_handle")) or _text(tagged_dict.get("creator")) or _text(original_dict.get("Creator")),
        "Creator Display": _text(tagged_dict.get("creator_display")),
        "Caption": _text(tagged_dict.get("caption")) or _text(original_dict.get("Caption")),
        "Followers": _creator_followers(raw_record) or _number(original_dict.get("Followers")),
        "Views": _number(tagged_dict.get("plays")),
        "Likes": _number(tagged_dict.get("likes")),
        "Comments": _number(tagged_dict.get("comments")),
        "Shares": _number(tagged_dict.get("shares")),
        "Saves": _number(tagged_dict.get("saves")),
        "Track From TikTok": _text(tagged_dict.get("music_name")),
        "Artist From TikTok": _text(tagged_dict.get("music_author")),
        "Is Slideshow": _truthy(tagged_dict.get("is_slideshow")),
        "Cover URL": _text(tagged_dict.get("cover_url")),
        "Video URL": _text(tagged_dict.get("video_url")),
        "Narrative": _text(tagged_dict.get("Narrative")),
        "Creative Type": creative_type,
        "Content Details": _text(tagged_dict.get("Content Details")),
        "Confidence": float(tagged_dict.get("confidence") or 0),
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
        "Manual Metrics Required": _truthy(tagged_dict.get("manual_metrics_required")),
        "Raw Apify Status": _text(raw_record.get("error")) or _text(raw_record.get("errorCode")) or "OK",
        "_raw_row_json": _text(tagged_dict.get("_raw_row_json")),
    })
    output.update(initial_label_audit(
        creative_type,
        tier=_text(tagged_dict.get("tier_used")),
        validation_status=validation_status,
    ))
    output["Total Engagement"] = sum(output.get(key, 0) for key in ["Likes", "Comments", "Shares", "Saves"])
    return output


def scrape_links(links: List[str], apify_token: str) -> List[Dict]:
    backend = load_backend()
    return list(backend.run_apify_tiktok_scraper_api(links, apify_token))


def tag_candidates(
    candidates: pd.DataFrame,
    records: List[Dict],
    gemini_key: str,
    apify_token: str,
    logs: Optional[List[str]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> pd.DataFrame:
    """Run final_update_2 by source/market/track and return the current UI schema."""
    if candidates.empty:
        return pd.DataFrame()
    backend = load_backend()
    logs = logs if logs is not None else []
    by_id, by_url = index_records(records)

    groups: OrderedDict[Tuple[str, str, str], List[Tuple[object, Dict]]] = OrderedDict()
    for _, row in candidates.iterrows():
        record = match_record(row, by_id, by_url)
        if not isinstance(record, dict):
            link = _text(row.get("Link"))
            record = {
                "url": link,
                "submittedVideoUrl": link,
                "error": "POST_NOT_FOUND",
                "errorCode": "POST_NOT_FOUND",
            }
        key = (_text(row.get("Source")), _text(row.get("Market")), _text(row.get("Track")))
        groups.setdefault(key, []).append((row, record))

    converted: List[Dict] = []
    completed = 0
    total = len(candidates)
    for (source, market, track), pairs in groups.items():
        group_records = [record for _, record in pairs]

        def row_done(_done, _group_total, output, tier):
            nonlocal completed
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
        for position, (original, raw_record) in enumerate(pairs):
            if position < len(tagged_rows):
                converted.append(_to_ui_row(original, tagged_rows[position], raw_record))
            else:
                converted.append(_to_ui_row(original, {
                    "Creative Type": "",
                    "confidence": 0,
                    "needs_human_review": True,
                    "validation_status": "review",
                    "validation_issues": "Backend returned no output row.",
                }, raw_record))
                completed += 1
                if on_progress:
                    on_progress(completed, total, "missing_output")

    return pd.DataFrame(converted)
