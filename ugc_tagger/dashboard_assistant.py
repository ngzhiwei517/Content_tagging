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
        "Use the dashboard evidence and clearly labelled general marketing ideas to suggest "
        "a practical campaign direction."
    ),
    "Recommend creators": (
        "Which creators should we consider engaging, and why, based only on these results?"
    ),
    "Draft a campaign brief": (
        "Turn the strongest dashboard findings into a concise campaign brief with an objective, "
        "audience hypothesis, creative direction, creator approach, and measurement plan."
    ),
    "Plan the next test": (
        "Recommend one focused creative test, including the hypothesis, variants, primary metric, "
        "and what result would support the idea."
    ),
}

PAGE_CHAT_SUGGESTIONS = {
    2: {
        "How do I add posts?": (
            "Explain how to use the Add posts page, including files versus pasted links, "
            "track, artist, market, and adding rows to the current batch."
        ),
        "What file can I upload?": (
            "Explain the supported upload files and the minimum required post-link data."
        ),
        "How should I fill track and market?": (
            "Explain when to enter track, artist, and market on the Add posts page."
        ),
    },
    3: {
        "How do I choose posts?": (
            "Explain Top posts versus Tag every link and how the ranking and optional filters work."
        ),
        "Which ranking metric should I use?": (
            "Explain when a marketing user should rank by views, engagement, or engagement rate."
        ),
        "How does the date range work?": (
            "Explain how to use the date range and optional window on the Select posts page."
        ),
    },
    4: {
        "What happens during tagging?": (
            "Explain the Run tagging page, automatic batch protection, saved progress, and resuming."
        ),
        "What if a key reaches its limit?": (
            "Explain how progress is preserved and how to continue after the Gemini or Apify key is updated."
        ),
    },
    5: {
        "How do I review a post?": (
            "Explain the Review page and the Keep, Edit, and Remove actions."
        ),
        "What should I check before keeping it?": (
            "Explain which post details and suggested tags a marketing user should verify."
        ),
    },
    6: DASHBOARD_CHAT_SUGGESTIONS,
}

PAGE_TITLES = {
    2: "Add posts",
    3: "Select posts",
    4: "Run tagging",
    5: "Review",
    6: "Summary and export",
}

PAGE_HELP_ANSWERS = {
    2: (
        "### Add posts\n"
        "- Upload CSV/XLSX files, or paste one TikTok or Instagram link per line.\n"
        "- Confirm the track name; change the detected artist or market only when needed.\n"
        "- Add the rows to the current batch. Files and pasted links are combined.\n"
        "- Duplicate links are removed automatically."
    ),
    3: (
        "### Select posts\n"
        "- Choose **Top posts** for a focused sample or **Tag every link** for the complete batch.\n"
        "- For Top posts, choose a ranking metric such as Total Engagement.\n"
        "- Apply grouping, market, platform, track, source, or date filters only when needed.\n"
        "- Preview the selection before continuing."
    ),
    4: (
        "### Run tagging\n"
        "- Start tagging and leave the page open while the current chunk runs.\n"
        "- Large batches save completed progress between chunks.\n"
        "- If a key reaches its limit, update it and resume the saved job.\n"
        "- Already completed posts should not need to be tagged again."
    ),
    5: (
        "### Review posts\n"
        "- Check the preview, creator, market, Creative Type, Narrative, and any drama details.\n"
        "- Choose **Keep** when the result is correct.\n"
        "- Edit any incorrect label or detail directly.\n"
        "- Choose **Remove** for an unusable post."
    ),
    6: (
        "### Review and export\n"
        "- Use filters or Creative Type shortcuts to focus the dashboard.\n"
        "- Review the KPI, creative, market, track, sound, post, and creator sections.\n"
        "- Download the final CSV/XLSX or internal QA report when ready."
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


def _answer_text(value: object, *, limit: int = 6000) -> str:
    """Keep intentional Markdown line breaks in generated chat responses."""
    if value is None:
        return ""
    cleaned = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return cleaned[:limit].rstrip()


def chat_history_markdown(
    messages: Optional[Iterable[Mapping[str, object]]],
    *,
    page_title: str = "Taggy conversation",
) -> str:
    """Create a local, readable export without persisting the conversation."""
    lines = [f"# {page_title}", ""]
    for message in list(messages or []):
        role = _text(message.get("role"), limit=20).casefold()
        content = _answer_text(message.get("content"))
        if role not in {"user", "assistant"} or not content:
            continue
        lines.extend([f"## {'User' if role == 'user' else 'Taggy'}", "", content, ""])
    return "\n".join(lines).rstrip() + "\n"


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
    # Uploaded files can legitimately mix ISO dates, locale-style dates and
    # timestamps. Pandas 2.x requires the explicit mixed parser to avoid a
    # noisy per-value fallback warning on every Streamlit rerun.
    dates = pd.to_datetime(
        _series(frame, "Date"),
        errors="coerce",
        utc=True,
        format="mixed",
    )
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
- Use only DASHBOARD_DATA for claims about the current results. Do not use the web, saved memory, or unstated facts.
- Treat DASHBOARD_DATA as the source of truth. Previous chat messages provide conversational context only and are not evidence.
- Support findings with the relevant figures. Do not invent missing metrics or claim that correlation proves causation.
- You may use general, timeless marketing knowledge for campaign ideas, briefs, and test designs. Put it under **AI suggestions** and never present it as dashboard evidence.
- Clearly label campaign ideas and next steps as recommendations or tests, not measured facts or guaranteed outcomes.
- If the dashboard does not contain enough evidence, say what is missing.

Response format:
- Keep the answer below 300 words unless the user explicitly asks for more detail.
- Start with one direct sentence, then use 2 to 4 short Markdown headings and bullet points.
- For analysis or campaign questions, use **Dashboard evidence**, **AI suggestions**, and **Watch-outs** when relevant.
- Use no more than 3 bullets per section and keep each bullet to 1 or 2 sentences.
- Do not use Markdown tables, walls of text, or raw heading markers inside paragraphs.

DASHBOARD_DATA:
{context_json}

SESSION_CHAT_HISTORY:
{json.dumps(safe_history, ensure_ascii=False)}

USER_QUESTION:
{_text(question, limit=1200)}
"""


def page_help_answer(step: int, question: str) -> str:
    """Answer common page-usage questions locally without an API call."""
    normalized = _text(question, limit=1200).casefold()
    help_markers = [
        "how do i use",
        "how to use",
        "how do i start",
        "what do i do",
        "what should i do",
        "guide me",
        "help me use",
        "how does this page",
        "explain ",
    ]
    if any(marker in normalized for marker in help_markers):
        return PAGE_HELP_ANSWERS.get(int(step), "")
    return ""


def build_page_assistant_prompt(
    *,
    step: int,
    question: str,
    context_json: str,
    history: Optional[Iterable[Mapping[str, object]]] = None,
) -> str:
    """Ground Taggy in the current workflow page and available batch data."""
    page_title = PAGE_TITLES.get(int(step), "UGC tagging tool")
    dashboard_prompt = build_dashboard_prompt(question, context_json, history)
    return f"""You are Taggy, a friendly guide inside a UGC post tagging tool.

CURRENT_PAGE: {page_title}

Page guidance:
{PAGE_HELP_ANSWERS.get(int(step), "Help the user understand the current workflow page.")}

Additional rules:
- First answer questions about how to use CURRENT_PAGE directly and step by step.
- Never claim that you clicked, uploaded, scraped, tagged, saved, or changed anything.
- Never ask for, repeat, or expose API keys or tokens.
- For data questions, follow all grounding rules in the dashboard prompt below.
- When dashboard data is empty, do not invent results; provide workflow guidance only.

{dashboard_prompt}
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
        answer = _answer_text(request_fn(model, prompt))
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
                max_output_tokens=700,
            ),
        )
        answer = _answer_text(getattr(response, "text", ""))
    if not answer:
        raise RuntimeError("Dashboard assistant returned an empty answer")
    return answer


def generate_page_assistant_answer(
    *,
    api_key: str,
    model: str,
    step: int,
    question: str,
    context_json: str,
    history: Optional[Iterable[Mapping[str, object]]] = None,
    request_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Generate one page-aware Taggy response with the existing Gemini client."""
    prompt = build_page_assistant_prompt(
        step=step,
        question=question,
        context_json=context_json,
        history=history,
    )
    if request_fn is not None:
        answer = _answer_text(request_fn(model, prompt))
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
                max_output_tokens=700,
            ),
        )
        answer = _answer_text(getattr(response, "text", ""))
    if not answer:
        raise RuntimeError("Taggy returned an empty answer")
    return answer
