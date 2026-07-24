"""Helpers for optional manual completion of unavailable post metrics."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional

import pandas as pd


METRIC_COLUMNS = ("Views", "Likes", "Comments", "Shares", "Saves")
MANUAL_METRIC_AUDIT_COLUMNS = (
    "Manual Metrics Source",
    "Manual Metrics Fields",
    "Manual Metrics Captured At",
)

_MISSING_TEXT = {
    "",
    "-",
    "—",
    "n/a",
    "na",
    "nan",
    "none",
    "not available",
    "null",
    "unknown",
}
_SUFFIX_MULTIPLIERS = {
    "": Decimal("1"),
    "k": Decimal("1000"),
    "m": Decimal("1000000"),
    "b": Decimal("1000000000"),
}
_METRIC_NAME_LOOKUP = {name.casefold(): name for name in METRIC_COLUMNS}


def _is_missing_scalar(value) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() in _MISSING_TEXT


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _unavailable_metric_names(value) -> set[str]:
    unavailable = set()
    for part in re.split(r"[,;|]", "" if value is None else str(value)):
        canonical = _METRIC_NAME_LOOKUP.get(part.strip().casefold())
        if canonical:
            unavailable.add(canonical)
    return unavailable


def missing_metric_names(row: Mapping) -> list[str]:
    """Return only metrics that are genuinely unavailable on a review row.

    Zero remains a valid metric unless the backend explicitly marked metrics as
    missing or the row came from a scraper/manual-metrics exception.
    """

    unavailable = _unavailable_metric_names(row.get("Metrics Unavailable", ""))
    exception_row = (
        _truthy(row.get("Manual Metrics Required", False))
        or str(row.get("Tier Used", "")).strip().casefold()
        in {"scraper_exception", "sensitive_human_review"}
    )
    missing = []
    for metric in METRIC_COLUMNS:
        value = row.get(metric)
        if metric in unavailable or _is_missing_scalar(value):
            missing.append(metric)
        elif exception_row:
            try:
                if Decimal(str(value).replace(",", "").strip()) == 0:
                    missing.append(metric)
            except (InvalidOperation, ValueError):
                missing.append(metric)
    return missing


def parse_manual_metric(value) -> Optional[int]:
    """Parse an optional non-negative count, including comma and K/M/B forms."""

    if _is_missing_scalar(value):
        return None
    text = re.sub(r"[\s,]+", "", str(value)).casefold()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", text)
    if not match:
        raise ValueError(f"Use a whole number or K/M/B format, not {value!r}.")
    try:
        parsed = Decimal(match.group(1)) * _SUFFIX_MULTIPLIERS[match.group(2)]
    except InvalidOperation as exc:
        raise ValueError(f"Could not read metric value {value!r}.") from exc
    if parsed < 0 or parsed != parsed.to_integral_value():
        raise ValueError(f"Metric value {value!r} must resolve to a whole number.")
    return int(parsed)


def build_manual_metric_updates(
    row: Mapping,
    raw_inputs: Mapping[str, object],
    *,
    captured_at: Optional[str] = None,
) -> dict:
    """Build metric and audit updates without converting blanks to zero."""

    missing = missing_metric_names(row)
    unavailable = _unavailable_metric_names(row.get("Metrics Unavailable", ""))
    filled = []
    updates = {}

    for metric in missing:
        parsed = parse_manual_metric(raw_inputs.get(metric))
        if parsed is None:
            updates[metric] = None
            unavailable.add(metric)
        else:
            updates[metric] = parsed
            unavailable.discard(metric)
            filled.append(metric)

    updates["Metrics Unavailable"] = ", ".join(
        metric for metric in METRIC_COLUMNS if metric in unavailable
    )
    updates["Manual Metrics Required"] = False

    if filled:
        previous = _unavailable_metric_names(row.get("Manual Metrics Fields", ""))
        all_manual_fields = previous.union(filled)
        updates["Manual Metrics Source"] = "Manual review"
        updates["Manual Metrics Fields"] = ", ".join(
            metric for metric in METRIC_COLUMNS if metric in all_manual_fields
        )
        updates["Manual Metrics Captured At"] = captured_at or datetime.now(
            timezone.utc
        ).replace(microsecond=0).isoformat()

    return updates
