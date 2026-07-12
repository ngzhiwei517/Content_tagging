"""Reusable Creative Type evaluation helpers.

The product's main score is label coverage: a row passes when at least one of
the AI's one or two labels matches a manual label. Primary-label and exact-set
metrics remain available as stricter diagnostics.
"""

from __future__ import annotations

import re
from typing import List, Set

import pandas as pd


LABEL_ALIASES = {
    "media/infortainment": "media/infotainment",
    "media / infortainment": "media/infotainment",
    "media infotainment": "media/infotainment",
    "media/ information": "media/infotainment",
    "media/information": "media/infotainment",
    "media & infotainment": "media/infotainment",
    "media and infotainment": "media/infotainment",
    "movie/tv/drama edit": "movie/tv/drama edits",
    "movie / tv / drama edits": "movie/tv/drama edits",
    "movie /tv/drama edits": "movie/tv/drama edits",
    "celeb edits": "celebrity edits",
    "celebrity edit": "celebrity edits",
    "lipsync": "lip sync",
    "lip-sync": "lip sync",
}


def is_blank(value) -> bool:
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value or "").strip()
    return text == "" or text.lower() in {"nan", "none", "null", "na", "n/a", "-", "--"}


def normalize_label(label: str) -> str:
    value = re.sub(r"\s+", " ", str(label or "").strip().lower())
    value = re.sub(r"\s*/\s*", "/", value)
    value = value.replace("tv /", "tv/")
    return LABEL_ALIASES.get(value, value)


def split_label_list(value) -> List[str]:
    if is_blank(value):
        return []
    output: List[str] = []
    for part in str(value).split(","):
        label = normalize_label(part)
        if label and label not in output:
            output.append(label)
    return output


def split_labels(value) -> Set[str]:
    return set(split_label_list(value))


def primary_match(manual, ai) -> bool:
    manual_labels = split_labels(manual)
    ai_labels = split_label_list(ai)
    return bool(manual_labels and ai_labels and ai_labels[0] in manual_labels)


def contains_match(manual, ai) -> bool:
    return bool(split_labels(manual).intersection(split_labels(ai)))


def exact_match(manual, ai) -> bool:
    manual_labels = split_labels(manual)
    ai_labels = split_labels(ai)
    return bool(manual_labels) and manual_labels == ai_labels


def contains_reason(manual, ai) -> str:
    manual_labels = split_labels(manual)
    ai_list = split_label_list(ai)
    overlap = [label for label in ai_list if label in manual_labels]
    if not ai_list:
        return f"FAIL: AI label is blank. Expected: {', '.join(sorted(manual_labels))}"
    if overlap:
        return f"PASS: matching label found: {', '.join(overlap)}"
    return (
        f"FAIL: expected at least one of {', '.join(sorted(manual_labels))}. "
        f"AI predicted: {', '.join(ai_list)}"
    )


def primary_reason(manual, ai) -> str:
    manual_labels = split_labels(manual)
    ai_list = split_label_list(ai)
    if not ai_list:
        return f"FAIL: AI label is blank. Expected: {', '.join(sorted(manual_labels))}"
    if ai_list[0] in manual_labels:
        extras = [label for label in ai_list[1:] if label not in manual_labels]
        if extras:
            return f"PASS: primary label {ai_list[0]}. Extra AI label(s): {', '.join(extras)}"
        return f"PASS: primary label {ai_list[0]}"
    if any(label in manual_labels for label in ai_list[1:]):
        return (
            f"FAIL: expected label appears only as a secondary AI label. "
            f"Expected: {', '.join(sorted(manual_labels))}. AI primary: {ai_list[0]}"
        )
    return (
        f"FAIL: expected {', '.join(sorted(manual_labels))}. "
        f"AI predicted: {', '.join(ai_list)}"
    )
