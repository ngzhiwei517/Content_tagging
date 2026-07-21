"""Approved Gemini models for the v68.41.6 final-validation candidate."""

from __future__ import annotations

import re
from collections import OrderedDict


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
# Verification stays on the explicitly selected run model. In particular, a
# 3.1 run must not silently become a slower 3.1 + 3.5 hybrid.
TARGETED_VERIFIER_MODEL = DEFAULT_GEMINI_MODEL

GEMINI_MODEL_OPTIONS = OrderedDict([
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite - recommended"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash - slower, deeper analysis"),
])

SUPPORTED_GEMINI_MODELS = tuple(GEMINI_MODEL_OPTIONS.keys())


def normalize_gemini_model(value) -> str:
    """Return a supported model id, falling back safely to the baseline."""
    candidate = str(value or "").strip()
    return candidate if candidate in GEMINI_MODEL_OPTIONS else DEFAULT_GEMINI_MODEL


def gemini_model_label(value) -> str:
    model_id = normalize_gemini_model(value)
    return GEMINI_MODEL_OPTIONS[model_id]


def gemini_model_slug(value) -> str:
    model_id = normalize_gemini_model(value)
    return re.sub(r"[^a-z0-9]+", "_", model_id.lower()).strip("_")
