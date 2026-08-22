"""Build resumable CSV exports from normalized MelodyIQ API imports."""

from __future__ import annotations

import json
import math
from typing import Dict, Iterable, List, Mapping

import pandas as pd

from .final_update2_adapter import normalize_url


MELODYIQ_SCOPE_RANKS_COLUMN = "_MelodyIQ API Scope Ranks"
MELODYIQ_API_CSV_COLUMNS = [
    "MelodyIQ Impact Rank",
    "Platform",
    "Creator",
    "Link",
    "Market",
    "Date",
    "Followers",
    "Views",
    "Likes",
    "Comments",
    "Shares",
    "Saves",
    "Metrics Unavailable",
    "Total Engagement",
    "Engagement Rate",
    "Likes Rate",
    "Comments Rate",
    "Shares Rate",
    "Saves Rate",
    "Track",
    "Original Sound",
    "Campaign Artist",
    "Source",
]


def melodyiq_scope_key(
    report_id: str,
    *,
    creator_country: str = "",
    post_created_at_min: str = "",
    post_created_at_max: str = "",
) -> str:
    """Return a stable key for one report and server-side filter scope."""
    payload = {
        "report_id": str(report_id or "").strip()[:256],
        "creator_country": str(creator_country or "").strip().upper()[:100],
        "post_created_at_min": str(post_created_at_min or "").strip()[:10],
        "post_created_at_max": str(post_created_at_max or "").strip()[:10],
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def melodyiq_scope_details(scope_key: str) -> Dict[str, str]:
    """Return safe display metadata from a scope key."""
    try:
        raw = json.loads(str(scope_key or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "report_id": str(raw.get("report_id") or "").strip()[:256],
        "creator_country": str(raw.get("creator_country") or "").strip().upper()[:100],
        "post_created_at_min": str(raw.get("post_created_at_min") or "").strip()[:10],
        "post_created_at_max": str(raw.get("post_created_at_max") or "").strip()[:10],
    }


def _safe_rank(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def melodyiq_scope_rank_map(value) -> Dict[str, object]:
    """Parse one row's scope-to-rank membership map."""
    if isinstance(value, Mapping):
        raw = value
    else:
        try:
            raw = json.loads(str(value or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = {}
    if not isinstance(raw, Mapping):
        return {}
    parsed: Dict[str, object] = {}
    for key, rank in raw.items():
        clean_key = str(key or "").strip()
        if clean_key:
            parsed[clean_key] = _safe_rank(rank)
    return parsed


def merge_melodyiq_scope_rank_values(values: Iterable[object]) -> str:
    """Merge scope memberships when Current Batch deduplicates a post URL."""
    merged: Dict[str, object] = {}
    for value in values:
        merged.update(melodyiq_scope_rank_map(value))
    if not merged:
        return ""
    return json.dumps(merged, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def attach_melodyiq_scope_rows(
    raw_frame: pd.DataFrame,
    normalized_frame: pd.DataFrame,
    scope_key: str,
) -> pd.DataFrame:
    """Attach compact report membership and rank data to normalized API rows."""
    if not isinstance(normalized_frame, pd.DataFrame):
        return pd.DataFrame()
    tagged = normalized_frame.copy()
    if tagged.empty:
        return tagged

    rank_by_link: Dict[str, object] = {}
    if isinstance(raw_frame, pd.DataFrame) and not raw_frame.empty:
        for _, row in raw_frame.iterrows():
            link_key = normalize_url(row.get("Link"))
            if link_key and link_key not in rank_by_link:
                rank_by_link[link_key] = _safe_rank(row.get("MelodyIQ Impact Rank"))

    tagged[MELODYIQ_SCOPE_RANKS_COLUMN] = tagged.get(
        "Link", pd.Series("", index=tagged.index)
    ).map(
        lambda link: json.dumps(
            {scope_key: rank_by_link.get(normalize_url(link))},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return tagged


def melodyiq_scope_keys(frame: pd.DataFrame) -> List[str]:
    """Return scope keys in the order they first appear in Current Batch."""
    if not isinstance(frame, pd.DataFrame) or MELODYIQ_SCOPE_RANKS_COLUMN not in frame:
        return []
    keys: List[str] = []
    seen = set()
    for value in frame[MELODYIQ_SCOPE_RANKS_COLUMN].tolist():
        for key in melodyiq_scope_rank_map(value):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def melodyiq_scope_export_frame(frame: pd.DataFrame, scope_key: str) -> pd.DataFrame:
    """Return unique normalized posts already loaded for one API scope."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=MELODYIQ_API_CSV_COLUMNS)
    if MELODYIQ_SCOPE_RANKS_COLUMN not in frame:
        return pd.DataFrame(columns=MELODYIQ_API_CSV_COLUMNS)

    included = []
    ranks = []
    for value in frame[MELODYIQ_SCOPE_RANKS_COLUMN].tolist():
        rank_map = melodyiq_scope_rank_map(value)
        included.append(scope_key in rank_map)
        ranks.append(rank_map.get(scope_key))

    exported = frame.loc[included].copy()
    if exported.empty:
        return pd.DataFrame(columns=MELODYIQ_API_CSV_COLUMNS)
    exported["MelodyIQ Impact Rank"] = [
        rank for rank, keep in zip(ranks, included) if keep
    ]
    exported["Source"] = "MelodyIQ API"
    exported["Input Type"] = "MelodyIQ API"
    exported = exported.drop(columns=[MELODYIQ_SCOPE_RANKS_COLUMN], errors="ignore")
    if "Link" in exported:
        exported = exported.drop_duplicates(subset=["Link"], keep="first")
    exported["_rank_sort"] = pd.to_numeric(
        exported["MelodyIQ Impact Rank"], errors="coerce"
    )
    exported = exported.sort_values("_rank_sort", kind="stable", na_position="last")
    exported = exported.drop(columns=["_rank_sort"])
    columns = [column for column in MELODYIQ_API_CSV_COLUMNS if column in exported]
    return exported.loc[:, columns].reset_index(drop=True)
