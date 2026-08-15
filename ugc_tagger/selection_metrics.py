"""Helpers for metric-aware Top N selection.

Selection happens before AI tagging, so rows containing only post links must be
measured before they can be ranked by performance.  These helpers deliberately
contain no Streamlit or provider calls, which keeps the decision and merge
logic inexpensive to test.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import pandas as pd


METRICS_REFRESH_ATTEMPTED = frozenset({"refreshed", "partial", "not refreshed"})

RANK_METRIC_DEPENDENCIES = {
    "Total Engagement": ("Total Engagement",),
    "Engagement Rate": ("Views", "Total Engagement"),
    "Likes Rate": ("Views", "Likes"),
    "Comments Rate": ("Views", "Comments"),
    "Shares Rate": ("Views", "Shares"),
    "Saves Rate": ("Views", "Saves"),
}

METRIC_REFRESH_COLUMNS = (
    "Creator",
    "Caption",
    "Followers",
    "Views",
    "Likes",
    "Comments",
    "Shares",
    "Saves",
    "Total Engagement",
    "Engagement Rate",
    "Likes Rate",
    "Comments Rate",
    "Shares Rate",
    "Saves Rate",
    "Metrics Status",
    "Metrics Unavailable",
)


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _positive_number(value) -> bool:
    """Return whether an unfetched input contains useful ranking evidence."""
    text = _text(value).replace(",", "").replace("%", "")
    if not text:
        return False
    try:
        return float(text) > 0
    except (TypeError, ValueError):
        return False


def metric_refresh_was_attempted(frame: pd.DataFrame) -> bool:
    """Return True when every row already completed a metrics retrieval attempt."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Metrics Status" not in frame.columns:
        return False
    statuses = frame["Metrics Status"].map(lambda value: _text(value).casefold())
    return bool(statuses.isin(METRICS_REFRESH_ATTEMPTED).all())


def _ranking_metrics_missing_mask(
    frame: pd.DataFrame,
    rank_metrics: Sequence[str] | str | None,
) -> pd.Series:
    """Return a row-aligned mask for posts that still need ranking metrics."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(False, index=getattr(frame, "index", None), dtype=bool)

    metrics: Iterable[str]
    if isinstance(rank_metrics, str):
        metrics = (rank_metrics,)
    else:
        metrics = tuple(rank_metrics or ("Total Engagement",))

    dependencies = {
        dependency
        for metric in metrics
        for dependency in RANK_METRIC_DEPENDENCIES.get(metric, (metric,))
    }
    needs_refresh = []
    for _, row in frame.iterrows():
        status = _text(row.get("Metrics Status")).casefold()
        needs_refresh.append(
            status not in METRICS_REFRESH_ATTEMPTED
            and any(not _positive_number(row.get(column)) for column in dependencies)
        )
    return pd.Series(needs_refresh, index=frame.index, dtype=bool)


def ranking_metrics_missing_count(
    frame: pd.DataFrame,
    rank_metrics: Sequence[str] | str | None,
) -> int:
    """Count rows that need retrieval before a requested ranking is defensible.

    Provider-attempted rows are considered final even when a platform did not
    return a metric.  Their unavailable values can then sort to the bottom
    without repeatedly spending credits on the same inaccessible post.
    """
    return int(_ranking_metrics_missing_mask(frame, rank_metrics).sum())


def pasted_links_requiring_metrics(
    frame: pd.DataFrame,
    rank_metrics: Sequence[str] | str | None,
) -> pd.DataFrame:
    """Return only pasted-link rows missing metrics needed for Top N ranking.

    Uploaded files normally carry their own performance columns, so they must
    never trigger a potentially large provider run during selection.  Their
    existing values remain in the full candidate pool and are still ranked.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Source" not in frame.columns:
        return frame.iloc[0:0].copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()

    pasted_mask = frame["Source"].map(
        lambda value: _text(value).casefold() == "pasted links"
    )
    missing_mask = _ranking_metrics_missing_mask(frame, rank_metrics)
    return frame.loc[pasted_mask & missing_mask].copy().reset_index(drop=True)


def merge_refreshed_metrics(
    batch: pd.DataFrame,
    refreshed: pd.DataFrame,
    *,
    normalize_url: Callable[[str], str],
) -> pd.DataFrame:
    """Merge refreshed post metrics back into a batch without changing its order."""
    if not isinstance(batch, pd.DataFrame) or batch.empty:
        return batch.copy() if isinstance(batch, pd.DataFrame) else pd.DataFrame()
    if not isinstance(refreshed, pd.DataFrame) or refreshed.empty:
        return batch.copy()

    refreshed_by_link = {}
    for _, row in refreshed.iterrows():
        key = normalize_url(_text(row.get("Link")))
        if key:
            refreshed_by_link[key] = row

    out = batch.copy()
    for index, original in out.iterrows():
        key = normalize_url(_text(original.get("Link")))
        update = refreshed_by_link.get(key)
        if update is None:
            continue
        for column in METRIC_REFRESH_COLUMNS:
            if column not in refreshed.columns:
                continue
            value = update.get(column)
            if column in {"Creator", "Caption"} and not _text(value):
                continue
            out.at[index, column] = value
    return out
