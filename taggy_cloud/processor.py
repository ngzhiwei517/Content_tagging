"""Headless wrapper around the existing, reviewed Taggy adapter."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from .sanitize import sanitize_mapping


def safe_processing_error_code(exc: BaseException) -> str:
    """Return a non-sensitive error category suitable for job status."""
    chain = []
    current: BaseException | None = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    text = " ".join(str(item) for item in chain).upper()
    if any(marker in text for marker in ("401", "403", "UNAUTHENTICATED", "PERMISSION_DENIED")):
        return "PROVIDER_ACCESS"
    if any(marker in text for marker in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT")):
        return "PROVIDER_QUOTA"
    if any(marker in text for marker in ("TIMEOUT", "TIMED OUT", "503", "UNAVAILABLE", "CONNECTION")):
        return "PROVIDER_TEMPORARY"
    return f"PROCESSING_{type(exc).__name__.upper()}"[:80]


def error_is_retryable(error_code: str) -> bool:
    return error_code in {"PROVIDER_QUOTA", "PROVIDER_TEMPORARY"}


class TaggyPostProcessor:
    """Process exactly one post through the existing adapter contract."""

    def __init__(self, gemini_key: str, apify_token: str) -> None:
        self.gemini_key = str(gemini_key or "").strip()
        self.apify_token = str(apify_token or "").strip()
        if not self.gemini_key or not self.apify_token:
            raise ValueError("Gemini and Apify provider access must be configured.")

    def process(self, post: Dict[str, Any], model: str) -> Dict[str, Any]:
        from ugc_tagger.final_update2_adapter import scrape_links, tag_candidates

        row = dict(post or {})
        link = str(row.get("Link") or row.get("link") or "").strip()
        if not link:
            raise ValueError("A supported post link is required.")
        row["Link"] = link
        candidates = pd.DataFrame([row])
        records = scrape_links([link], self.apify_token)
        result = tag_candidates(
            candidates,
            records,
            self.gemini_key,
            self.apify_token,
            logs=[],
            gemini_model=model,
        )
        if result.empty:
            raise RuntimeError("The tagging adapter returned no result row.")
        return sanitize_mapping(result.iloc[0].to_dict())
