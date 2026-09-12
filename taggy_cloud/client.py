"""Small Streamlit-safe client for the optional Taggy job service."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

from .sanitize import json_safe, sanitize_mapping


class CloudBackendError(RuntimeError):
    """A safe client error that never includes credentials or response bodies."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "CLOUD_BACKEND_ERROR")


def dataframe_records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    return [sanitize_mapping(row) for row in frame.to_dict(orient="records")]


class TaggyCloudClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self.session = session or requests.Session()
        if not self.base_url.startswith(("https://", "http://")) or not self.api_key:
            raise ValueError("Cloud backend URL and API key are required.")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Taggy-Backend-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        try:
            response = getattr(self.session, method)(
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise CloudBackendError(
                "CLOUD_BACKEND_UNAVAILABLE",
                "The cloud tagging service could not be reached. Progress remains saved.",
            ) from exc
        if response.status_code == 401:
            raise CloudBackendError(
                "CLOUD_BACKEND_ACCESS",
                "Cloud tagging access is not configured correctly.",
            )
        if response.status_code == 404:
            raise CloudBackendError(
                "CLOUD_JOB_NOT_FOUND",
                "The saved cloud job could not be found.",
            )
        if response.status_code >= 400:
            raise CloudBackendError(
                f"CLOUD_BACKEND_HTTP_{response.status_code}",
                "The cloud tagging service could not complete this request.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CloudBackendError(
                "CLOUD_BACKEND_RESPONSE",
                "The cloud tagging service returned an invalid response.",
            ) from exc
        if not isinstance(payload, dict):
            raise CloudBackendError(
                "CLOUD_BACKEND_RESPONSE",
                "The cloud tagging service returned an invalid response.",
            )
        return payload

    def create_job(
        self,
        *,
        job_id: str,
        recovery_id: str,
        model: str,
        posts: pd.DataFrame | Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rows = (
            dataframe_records(posts)
            if isinstance(posts, pd.DataFrame)
            else [sanitize_mapping(row) for row in posts]
        )
        return self._request(
            "post",
            "/v1/jobs",
            json={
                "job_id": job_id,
                "recovery_id": recovery_id,
                "model": model,
                "posts": rows,
            },
        )

    def status(self, job_id: str) -> Dict[str, Any]:
        return self._request("get", f"/v1/jobs/{job_id}")

    def results(self, job_id: str) -> List[Dict[str, Any]]:
        payload = self._request("get", f"/v1/jobs/{job_id}/results")
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise CloudBackendError(
                "CLOUD_BACKEND_RESPONSE",
                "The cloud tagging service returned invalid results.",
            )
        ordered = sorted(
            (row for row in rows if isinstance(row, dict)),
            key=lambda row: int(row.get("position") or 0),
        )
        return [
            row["result"]
            for row in ordered
            if isinstance(row.get("result"), dict)
        ]

    def resume(self, job_id: str) -> Dict[str, Any]:
        return self._request("post", f"/v1/jobs/{job_id}/resume")
