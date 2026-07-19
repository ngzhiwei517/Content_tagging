"""Schema adapter between the v55 marketing UI and final_update_2 backend."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from final_update2_backend import load_backend
from drama_analysis import (
    DRAMA_EXPORT_COLUMNS,
    DRAMA_REVIEW_OPTIONS,
    build_review_drama_updates,
    drama_review_defaults,
    has_drama_label,
)


ProgressCallback = Callable[[int, int, str], None]


MARKETING_EXPORT_COLUMNS = [
    "Source", "Link", "Market", "Track", "Campaign Artist", "Creator", "Followers", "KOL Size",
    "Views", "Likes", "Comments", "Shares", "Saves", "Total Engagement",
    "Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate",
    # Detailed drama fields are deliberately consolidated into Content Details
    # so the marketing export remains one clean, readable table.
    "Narrative", "Creative Type", "Content Details",
]

QA_AUDIT_COLUMNS = [
    "Original AI Labels", "Final Labels", "Human Reviewed", "Human Edited",
    "Label History", "Verifier Status", "Verifier Input Labels",
    "Verifier Output Labels", "Verifier Confidence", "Verifier Reason",
    "Verifier Evidence", "Verifier Triggers",
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
        "Carousel": "Photo carousel",
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
    creative_type = _text(tagged_dict.get("Creative Type")) or "Others"
    narrative = _resolved_narrative_suggestion(tagged_dict, creative_type)
    qa_reason = " | ".join(
        value for value in [
            _text(tagged_dict.get("validation_issues")),
            _text(tagged_dict.get("tier3_reason")),
            _text(tagged_dict.get("remove_reason")),
        ] if value
    )

    output.update({
        "App Version": "v68.39",
        "Link": _text(tagged_dict.get("tiktok_url")) or _text(original_dict.get("Link")),
        # Campaign Market is user-provided business context. Do not fall back to
        # TikTok/Apify locationCreated, which describes post or creator origin.
        "Market": _text(original_dict.get("Market")),
        "Market Source": "Uploaded file / user input" if _text(original_dict.get("Market")) else "Not provided",
        "Track": (
            _text(original_dict.get("Track"))
            or _text(tagged_dict.get("track"))
            or _text(tagged_dict.get("music_name"))
            or _record_music_name(raw_record)
        ),
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

    groups: OrderedDict[Tuple[str, str, str], List[Tuple[int, object, Dict]]] = OrderedDict()
    for input_position, (_, row) in enumerate(candidates.iterrows()):
        record = match_record(row, by_id, by_url)
        if not isinstance(record, dict):
            link = _text(row.get("Link"))
            record = {
                "url": link,
                "submittedVideoUrl": link,
                "error": "POST_NOT_FOUND",
                "errorCode": "POST_NOT_FOUND",
            }
        resolved_track = _resolved_campaign_track(row, record)
        key = (_text(row.get("Source")), _text(row.get("Market")), resolved_track)
        groups.setdefault(key, []).append((input_position, row, record))

    converted: List[Tuple[int, Dict]] = []
    completed = 0
    total = len(candidates)
    for (source, market, track), pairs in groups.items():
        group_records = [record for _, _, record in pairs]

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
        for position, (input_position, original, raw_record) in enumerate(pairs):
            if position < len(tagged_rows):
                converted.append((input_position, _to_ui_row(original, tagged_rows[position], raw_record)))
            else:
                converted.append((input_position, _to_ui_row(original, {
                    "Creative Type": "",
                    "confidence": 0,
                    "needs_human_review": True,
                    "validation_status": "review",
                    "validation_issues": "Backend returned no output row.",
                }, raw_record)))
                completed += 1
                if on_progress:
                    on_progress(completed, total, "missing_output")

    # Source/market/track grouping is an implementation detail. Restore the
    # exact upload/paste sequence before handing rows back to the UI.
    converted.sort(key=lambda item: item[0])
    return pd.DataFrame([row for _, row in converted]).reset_index(drop=True)
