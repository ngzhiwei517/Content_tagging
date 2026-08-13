"""Grounded, session-only assistant helpers for the marketing dashboard."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Callable, Dict, Iterable, List, Mapping, Optional

import pandas as pd


DASHBOARD_CHAT_SUGGESTIONS = {
    "Summarise key insights": "Summarise the most important insights in this dashboard.",
    "Suggest a campaign": (
        "Based only on these dashboard results, suggest a campaign direction and explain "
        "which evidence supports it."
    ),
    "Recommend creators": (
        "Which creators should we consider engaging, and why, based only on these results?"
    ),
    "Suggest the next creative test": (
        "Which creative direction should we test next, and what should the test compare?"
    ),
}

MAX_GROUP_ROWS = 12
MAX_POST_ROWS = 10
MAX_CREATOR_ROWS = 10
MAX_HISTORY_MESSAGES = 6


def _text(value: object, *, limit: int = 240) -> str:
    if value is None or value is pd.NA:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    cleaned = " ".join(str(value).strip().split())
    return cleaned[:limit]


def _number(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 3)


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")


def _first_present(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return frame[column]
    return pd.Series([""] * len(frame), index=frame.index, dtype="object")


def _sum_or_none(series: pd.Series) -> Optional[float]:
    numeric = pd.to_numeric(series, errors="coerce")
    if not numeric.notna().any():
        return None
    return _number(numeric.sum(min_count=1))


def _mean_or_none(series: pd.Series) -> Optional[float]:
    numeric = pd.to_numeric(series, errors="coerce")
    if not numeric.notna().any():
        return None
    return _number(numeric.mean())


def _performance_record(frame: pd.DataFrame) -> Dict[str, object]:
    return {
        "posts": int(len(frame)),
        "total_views": _sum_or_none(frame["_dashboard_views"]),
        "total_engagement": _sum_or_none(frame["_dashboard_engagement"]),
        "average_engagement_rate_percent": _mean_or_none(
            frame["_dashboard_engagement_rate"]
        ),
    }


def _group_summary(frame: pd.DataFrame, column: str, label: str) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    values = frame[column].map(lambda value: _text(value) or "Not specified")
    grouped = frame.assign(_dashboard_group=values).groupby(
        "_dashboard_group", sort=False, dropna=False
    )
    for value, group in grouped:
        record: Dict[str, object] = {label: _text(value) or "Not specified"}
        record.update(_performance_record(group))
        records.append(record)
    records.sort(
        key=lambda item: (
            item.get("total_views") is not None,
            item.get("total_views") or 0,
            item.get("total_engagement") or 0,
        ),
        reverse=True,
    )
    return records[:MAX_GROUP_ROWS]


def _date_range(frame: pd.DataFrame) -> Dict[str, Optional[str]]:
    dates = pd.to_datetime(_series(frame, "Date"), errors="coerce", utc=True)
    if not dates.notna().any():
        return {"start": None, "end": None}
    return {
        "start": dates.min().date().isoformat(),
        "end": dates.max().date().isoformat(),
    }


def build_dashboard_context(filtered: pd.DataFrame) -> Dict[str, object]:
    """Return a compact allowlisted snapshot of the current filtered dashboard."""
    if filtered is None:
        filtered = pd.DataFrame()
    frame = filtered.copy()

    frame["_dashboard_platform"] = _first_present(
        frame, ["Platform Display", "Platform"]
    ).map(lambda value: _text(value) or "Not specified")
    frame["_dashboard_market"] = _first_present(
        frame, ["Market Display", "Market"]
    ).map(lambda value: _text(value) or "Other")
    frame["_dashboard_track"] = _first_present(
        frame, ["Track Display", "Track"]
    ).map(lambda value: _text(value) or "Not specified")
    frame["_dashboard_creative_type"] = _first_present(
        frame, ["Primary Creative Type", "Creative Type"]
    ).map(lambda value: _text(value) or "Others")
    frame["_dashboard_creator"] = _series(frame, "Creator").map(
        lambda value: _text(value) or "Unknown"
    )
    frame["_dashboard_kol_size"] = _first_present(
        frame, ["KOL Size Display", "KOL Size"]
    ).map(lambda value: _text(value) or "Unknown")
    frame["_dashboard_views"] = pd.to_numeric(_series(frame, "Views"), errors="coerce")
    frame["_dashboard_engagement"] = pd.to_numeric(
        _series(frame, "Total Engagement"), errors="coerce"
    )
    views = frame["_dashboard_views"].where(frame["_dashboard_views"].gt(0))
    frame["_dashboard_engagement_rate"] = (
        frame["_dashboard_engagement"].div(views).mul(100)
    )

    totals = _performance_record(frame)
    totals.update(
        {
            "platforms": sorted(set(frame["_dashboard_platform"].tolist())),
            "markets": sorted(set(frame["_dashboard_market"].tolist())),
            "tracks": sorted(set(frame["_dashboard_track"].tolist())),
            "date_range": _date_range(frame),
            "posts_without_views": int(frame["_dashboard_views"].isna().sum()),
        }
    )

    top_posts: List[Dict[str, object]] = []
    if not frame.empty:
        ranked_posts = frame.assign(
            _views_rank=frame["_dashboard_views"].fillna(-1),
            _engagement_rank=frame["_dashboard_engagement"].fillna(-1),
        ).sort_values(
            ["_views_rank", "_engagement_rank"], ascending=[False, False], kind="stable"
        )
        for _, row in ranked_posts.head(MAX_POST_ROWS).iterrows():
            top_posts.append(
                {
                    "creator": _text(row.get("_dashboard_creator")),
                    "platform": _text(row.get("_dashboard_platform")),
                    "market": _text(row.get("_dashboard_market")),
                    "track": _text(row.get("_dashboard_track")),
                    "creative_type": _text(row.get("_dashboard_creative_type")),
                    "content_subtype": (
                        _text(row.get("Content Subtype"))
                        or _text(row.get("Drama Content Category Display"))
                    ),
                    "narrative": _text(row.get("Narrative"), limit=360),
                    "views": _number(row.get("_dashboard_views")),
                    "total_engagement": _number(row.get("_dashboard_engagement")),
                    "engagement_rate_percent": _number(
                        row.get("_dashboard_engagement_rate")
                    ),
                }
            )

    top_creators: List[Dict[str, object]] = []
    if not frame.empty:
        creator_groups = frame.groupby(
            ["_dashboard_creator", "_dashboard_platform"],
            sort=False,
            dropna=False,
        )
        for (creator, platform), group in creator_groups:
            record: Dict[str, object] = {
                "creator": _text(creator) or "Unknown",
                "platform": _text(platform) or "Not specified",
                "market": _text(group["_dashboard_market"].iloc[0]) or "Other",
                "kol_size": _text(group["_dashboard_kol_size"].iloc[0]) or "Unknown",
                "followers": _number(
                    pd.to_numeric(_series(group, "Followers"), errors="coerce").max()
                ),
            }
            record.update(_performance_record(group))
            top_creators.append(record)
        top_creators.sort(
            key=lambda item: (
                item.get("total_engagement") is not None,
                item.get("total_engagement") or 0,
                item.get("total_views") or 0,
            ),
            reverse=True,
        )
        top_creators = top_creators[:MAX_CREATOR_ROWS]

    return {
        "scope": "Current filtered dashboard only",
        "totals": totals,
        "creative_type_summary": _group_summary(
            frame, "_dashboard_creative_type", "creative_type"
        ),
        "market_summary": _group_summary(frame, "_dashboard_market", "market"),
        "platform_summary": _group_summary(
            frame, "_dashboard_platform", "platform"
        ),
        "track_summary": _group_summary(frame, "_dashboard_track", "track"),
        "top_posts": top_posts,
        "top_creators": top_creators,
    }


def dashboard_context_json(filtered: pd.DataFrame) -> str:
    return json.dumps(
        build_dashboard_context(filtered),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def dashboard_context_signature(context_json: str) -> str:
    return hashlib.sha256(context_json.encode("utf-8")).hexdigest()


def build_dashboard_prompt(
    question: str,
    context_json: str,
    history: Optional[Iterable[Mapping[str, object]]] = None,
) -> str:
    safe_history: List[Dict[str, str]] = []
    for message in list(history or [])[-MAX_HISTORY_MESSAGES:]:
        role = _text(message.get("role"), limit=20).lower()
        content = _text(message.get("content"), limit=1200)
        if role in {"user", "assistant"} and content:
            safe_history.append({"role": role, "content": content})

    return f"""You are a concise marketing dashboard assistant.

Grounding rules:
- Use only DASHBOARD_DATA below. Do not use the web, external knowledge, saved memory, or unstated facts.
- Treat DASHBOARD_DATA as the source of truth. Previous chat messages provide conversational context only and are not evidence.
- Support findings with the relevant figures. Do not invent missing metrics or claim that correlation proves causation.
- Clearly label campaign ideas and next steps as recommendations or tests, not measured facts.
- If the dashboard does not contain enough evidence, say what is missing.
- Keep the answer practical, marketing-friendly, and concise. Use short bullets when useful.

DASHBOARD_DATA:
{context_json}

SESSION_CHAT_HISTORY:
{json.dumps(safe_history, ensure_ascii=False)}

USER_QUESTION:
{_text(question, limit=1200)}
"""


def generate_dashboard_answer(
    *,
    api_key: str,
    model: str,
    question: str,
    context_json: str,
    history: Optional[Iterable[Mapping[str, object]]] = None,
    request_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Generate an answer; ``request_fn`` keeps tests local and credit-free."""
    prompt = build_dashboard_prompt(question, context_json, history)
    if request_fn is not None:
        answer = _text(request_fn(model, prompt), limit=8000)
    else:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=45_000),
        )
        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1200,
            ),
        )
        answer = _text(getattr(response, "text", ""), limit=8000)
    if not answer:
        raise RuntimeError("Dashboard assistant returned an empty answer")
    return answer
