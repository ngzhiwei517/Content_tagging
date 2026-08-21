"""Small, provider-safe helpers for MelodyIQ preparation status copy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Tuple


# MelodyIQ does not expose a live ETA. These intentionally broad planning
# ranges are based only on the report's tracked-post volume and must never be
# presented as a provider guarantee.
_PREPARATION_ESTIMATE_BANDS = (
    (10_000, "5–20 minutes", 20 * 60),
    (100_000, "15–60 minutes", 60 * 60),
    (500_000, "30 minutes–2 hours", 2 * 60 * 60),
    (1_000_000, "1–4 hours", 4 * 60 * 60),
    (None, "2–8+ hours", 8 * 60 * 60),
)


def preparation_estimate(post_count: Any) -> Tuple[str, Optional[int]]:
    """Return a broad total-time label and its soft upper threshold."""
    try:
        count = max(int(float(post_count or 0)), 0)
    except (TypeError, ValueError, OverflowError):
        count = 0
    if count <= 0:
        return "Waiting for tracked-post count", None
    for upper_count, label, upper_seconds in _PREPARATION_ESTIMATE_BANDS:
        if upper_count is None or count <= upper_count:
            return label, upper_seconds
    return "2–8+ hours", 8 * 60 * 60


def elapsed_seconds(
    started_at: Any,
    *,
    now: Optional[datetime] = None,
) -> Optional[int]:
    """Return non-negative UTC elapsed seconds for an ISO timestamp."""
    text = str(started_at or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        started = datetime.fromisoformat(text)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    difference = current.astimezone(timezone.utc) - started.astimezone(timezone.utc)
    return max(int(difference.total_seconds()), 0)


def format_elapsed(seconds: Any) -> str:
    """Format a duration compactly for an auto-refreshing status line."""
    try:
        total = max(int(seconds), 0)
    except (TypeError, ValueError, OverflowError):
        return "Starting"
    if total < 60:
        return "Under 1 minute"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, remaining_minutes = divmod(minutes, 60)
    if remaining_minutes:
        return f"{hours} hr {remaining_minutes} min"
    return f"{hours} hr"
