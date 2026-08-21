"""Small, side-effect-free client for the optional MelodyIQ import flow.

The module deliberately contains no Streamlit state.  Credentials are supplied
by the caller and are never included in errors or persisted in checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd
import requests


DEFAULT_BASE_URL = "https://api.melodyiq.com"


class MelodyIQError(RuntimeError):
    """Base error with a concise, user-safe message."""


class MelodyIQAuthenticationError(MelodyIQError):
    """The configured API key is missing, invalid, or revoked."""


class MelodyIQLicenseError(MelodyIQError):
    """The license expired or a report-license limit was reached."""


class MelodyIQRateLimitError(MelodyIQError):
    """The shared MelodyIQ request quota was reached."""


def _safe_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if isinstance(payload, Mapping):
        value = payload.get("error") or payload.get("message")
        if value:
            return str(value).strip()
    return f"HTTP {response.status_code}"


@dataclass
class MelodyIQClient:
    """Authenticated HTTP client for the MelodyIQ v1 API."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    session: Optional[requests.Session] = None
    timeout: int = 45

    def __post_init__(self) -> None:
        self.api_key = str(self.api_key or "").strip()
        self.base_url = str(self.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.session = self.session or requests.Session()
        if not self.api_key:
            raise MelodyIQAuthenticationError(
                "MelodyIQ is not configured. Ask the app owner to add the API key."
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: Sequence[int] = (200,),
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        headers = {
            "accept": "application/json",
            "x-api-key": self.api_key,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                params=dict(params or {}),
                json=dict(json_body) if json_body is not None else None,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise MelodyIQError(
                "MelodyIQ could not be reached. Check the connection and try again."
            ) from exc
        if response.status_code in expected:
            return response

        detail = _safe_error_message(response)
        if response.status_code == 401:
            raise MelodyIQAuthenticationError(
                "The MelodyIQ API key is invalid or has been revoked."
            )
        if response.status_code == 403:
            raise MelodyIQLicenseError(
                "MelodyIQ rejected the request because the license expired or a report limit was reached."
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            suffix = f" Try again in {retry_after} seconds." if retry_after else ""
            raise MelodyIQRateLimitError(
                "The shared MelodyIQ request limit was reached." + suffix
            )
        raise MelodyIQError(f"MelodyIQ request failed: {detail}.")

    @staticmethod
    def _json(response: requests.Response) -> Dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise MelodyIQError("MelodyIQ returned an unreadable response.") from exc
        if not isinstance(payload, dict):
            raise MelodyIQError("MelodyIQ returned an unexpected response.")
        return payload

    def search_sounds(
        self,
        title: str,
        *,
        artists: Optional[Sequence[str]] = None,
        page: int = 1,
        per_page: int = 20,
        sort_field: str = "postCount",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "title": str(title or "").strip(),
            "page": max(int(page), 1),
            "perPage": min(max(int(per_page), 1), 100),
            "sortField": sort_field,
            "sortDirection": sort_direction,
        }
        clean_artists = [str(value).strip() for value in (artists or []) if str(value).strip()]
        if clean_artists:
            body["artists"] = clean_artists
        return self._json(
            self._request(
                "POST",
                "/v1/tktk/sounds/search",
                json_body=body,
            )
        )

    def create_report(
        self,
        name: str,
        sound_ids: Sequence[str],
        *,
        artists: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        ids = list(dict.fromkeys(str(value).strip() for value in sound_ids if str(value).strip()))
        if not ids:
            raise MelodyIQError("Select at least one MelodyIQ sound.")
        body: Dict[str, Any] = {
            "name": str(name or "Content Tagger import").strip(),
            "isPriorityReport": False,
            "isSuggestedSoundAutoAddEnabled": True,
            "tktk": {"soundIds": ids},
        }
        clean_artists = [str(value).strip() for value in (artists or []) if str(value).strip()]
        if clean_artists:
            body["artists"] = clean_artists
        return self._json(
            self._request("POST", "/v1/reports", expected=(200, 201), json_body=body)
        )

    def get_report(self, report_id: str) -> Dict[str, Any]:
        return self._json(self._request("GET", f"/v1/reports/{report_id}"))

    def refresh_report(self, report_id: str) -> None:
        # A report that is already refreshing may return 409.  It is safe to
        # continue polling that existing job instead of treating it as a failure.
        self._request(
            "POST",
            f"/v1/reports/{report_id}/refresh",
            expected=(200, 202, 204, 409),
        )

    def delete_report(self, report_id: str) -> None:
        self._request(
            "DELETE",
            f"/v1/reports/{report_id}",
            expected=(200, 202, 204),
        )

    def get_impactful_posts(
        self,
        report_id: str,
        *,
        page: int = 1,
        per_page: int = 100,
        sort_field: str = "viewCount",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        # Omit unused bounds completely. Sending Swagger's example {min: 0,
        # max: 0} values would filter out ordinary non-zero posts.
        params = {
            "page": max(int(page), 1),
            "perPage": min(max(int(per_page), 1), 100),
            "sortField": sort_field,
            "sortDirection": sort_direction,
        }
        return self._json(
            self._request(
                "GET",
                f"/v1/reports/{report_id}/tktk/impactful-posts",
                params=params,
            )
        )

    def get_all_impactful_posts(
        self,
        report_id: str,
        *,
        limit: int,
        sort_field: str = "viewCount",
        sort_direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        requested = max(int(limit), 1)
        posts: List[Dict[str, Any]] = []
        page = 1
        while len(posts) < requested:
            payload = self.get_impactful_posts(
                report_id,
                page=page,
                per_page=min(100, requested - len(posts)),
                sort_field=sort_field,
                sort_direction=sort_direction,
            )
            batch = payload.get("posts") or []
            if not isinstance(batch, list) or not batch:
                break
            posts.extend(item for item in batch if isinstance(item, dict))
            pagination = payload.get("pagination") or {}
            last_page = int(pagination.get("lastPage") or page)
            if page >= last_page:
                break
            page += 1
        return posts[:requested]

    def download_csv(self, url: str, *, max_rows: Optional[int] = None) -> pd.DataFrame:
        clean_url = str(url or "").strip()
        if not clean_url.startswith("https://"):
            raise MelodyIQError("The report export URL is unavailable.")
        response = None
        try:
            # Export URLs are signed/public Google Storage URLs and do not need
            # the MelodyIQ API key.
            response = self.session.get(
                clean_url,
                timeout=max(self.timeout, 120),
                stream=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MelodyIQError(
                "The MelodyIQ report CSV could not be downloaded. Try refreshing the report status."
            ) from exc
        try:
            row_limit = None if max_rows is None else max(int(max_rows), 1)
            # Parse directly from the HTTP stream. ``nrows`` can then stop the
            # read after the requested import size instead of loading a
            # million-row export into Streamlit memory first.
            response.raw.decode_content = True
            return pd.read_csv(response.raw, nrows=row_limit)
        except Exception as exc:
            raise MelodyIQError("The MelodyIQ report export is not a readable CSV.") from exc
        finally:
            if response is not None:
                response.close()


def impactful_posts_frame(posts: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Return a CSV-like frame compatible with the app's normal importer."""
    rows = []
    for post in posts:
        likes = post.get("likeCount")
        comments = post.get("commentCount")
        shares = post.get("shareCount")
        rows.append(
            {
                "Link": post.get("url"),
                "Date": post.get("postCreatedAt"),
                "Creator": post.get("creatorUsername"),
                "Market": post.get("creatorCountry"),
                "Followers": post.get("creatorFollowerCount"),
                "Views": post.get("viewCount"),
                "Likes": likes,
                "Comments": comments,
                "Shares": shares,
                "Saves": None,
                "Total Engagement": sum(
                    int(value or 0) for value in (likes, comments, shares)
                ),
                "Sound Name": post.get("soundId"),
                "MelodyIQ Impact Rank": post.get("rank"),
            }
        )
    return pd.DataFrame(rows)
