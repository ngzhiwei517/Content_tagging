"""Secret- and media-safe JSON conversion for durable cloud job state."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Dict

import pandas as pd


BLOCKED_FIELD = re.compile(
    r"api[ _-]*key|token|secret|password|authorization|"
    r"database[ _-]*url|connection[ _-]*string|"
    r"download(?:ed)?[ _-]*(?:media|video|image|audio)|"
    r"(?:media|video|image|audio)[ _-]*(?:bytes|blob|path)|"
    r"local[ _-]*(?:media|video|image|audio)|(?:^|[ _-])temp(?:orary)?[ _-]*path$",
    re.IGNORECASE,
)


def _blocked_key(value: Any) -> bool:
    return bool(BLOCKED_FIELD.search(str(value or "")))


def json_safe(value: Any):
    """Return strict JSON values while dropping binary and sensitive fields."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
            if not _blocked_key(key)
            and not isinstance(item, (bytes, bytearray, memoryview))
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except Exception:
            pass
    return str(value)


def sanitize_mapping(value: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = json_safe(dict(value or {}))
    return sanitized if isinstance(sanitized, dict) else {}
