import unittest
import io

import pandas as pd
import requests

from ugc_tagger.melodyiq_client import (
    MelodyIQAuthenticationError,
    MelodyIQClient,
    MelodyIQLicenseError,
    MelodyIQRateLimitError,
    impactful_posts_frame,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.content = content
        self.raw = io.BytesIO(content)
        self.raw.decode_content = False
        self.headers = headers or {}
        self.closed = False

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses=None, get_response=None):
        self.responses = list(responses or [])
        self.get_response = get_response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET_EXPORT", url, kwargs))
        if self.get_response is None:
            raise AssertionError("Unexpected export request")
        return self.get_response


class MelodyIQClientTests(unittest.TestCase):
    def test_search_uses_api_key_header_and_expected_body(self):
        session = FakeSession(
            [FakeResponse(payload={"sounds": [], "pagination": {"total": 0}})]
        )
        client = MelodyIQClient("test-key", session=session)

        result = client.search_sounds(
            "Every Summertime",
            artists=["NIKI"],
            per_page=20,
        )

        self.assertEqual(result["sounds"], [])
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.melodyiq.com/v1/tktk/sounds/search")
        self.assertEqual(kwargs["headers"]["x-api-key"], "test-key")
        self.assertEqual(kwargs["json"]["title"], "Every Summertime")
        self.assertEqual(kwargs["json"]["artists"], ["NIKI"])
        self.assertEqual(kwargs["json"]["sortField"], "postCount")

    def test_create_report_is_non_priority_adds_related_sounds_and_deduplicates_ids(self):
        session = FakeSession([FakeResponse(status_code=201, payload={"reportId": "r1"})])
        client = MelodyIQClient("test-key", session=session)

        result = client.create_report("API test", ["sound-1", "sound-1", "sound-2"])

        self.assertEqual(result["reportId"], "r1")
        body = session.calls[0][2]["json"]
        self.assertFalse(body["isPriorityReport"])
        self.assertTrue(body["isSuggestedSoundAutoAddEnabled"])
        self.assertEqual(body["tktk"]["soundIds"], ["sound-1", "sound-2"])

    def test_impactful_pagination_stops_at_requested_limit(self):
        first = [{"postId": str(index)} for index in range(100)]
        second = [{"postId": str(index)} for index in range(100, 150)]
        session = FakeSession(
            [
                FakeResponse(
                    payload={
                        "posts": first,
                        "pagination": {"currentPage": 1, "lastPage": 2},
                    }
                ),
                FakeResponse(
                    payload={
                        "posts": second,
                        "pagination": {"currentPage": 2, "lastPage": 2},
                    }
                ),
            ]
        )
        client = MelodyIQClient("test-key", session=session)

        posts = client.get_all_impactful_posts("r1", limit=125)

        self.assertEqual(len(posts), 125)
        self.assertEqual(session.calls[0][2]["params"]["perPage"], 100)
        self.assertEqual(session.calls[1][2]["params"]["perPage"], 25)
        self.assertNotIn("rank[min]", session.calls[0][2]["params"])

    def test_download_csv_honours_row_limit_without_api_key_header(self):
        csv_bytes = b"Link,Views\nhttps://www.tiktok.com/@a/video/1,10\nhttps://www.tiktok.com/@b/video/2,20\n"
        session = FakeSession(get_response=FakeResponse(content=csv_bytes))
        client = MelodyIQClient("test-key", session=session)

        frame = client.download_csv(
            "https://storage.googleapis.com/example/report.csv",
            max_rows=1,
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["Views"], 10)
        self.assertEqual(session.calls[0][0], "GET_EXPORT")
        self.assertNotIn("headers", session.calls[0][2])
        self.assertTrue(session.calls[0][2]["stream"])
        self.assertTrue(session.get_response.closed)

    def test_user_safe_error_mapping(self):
        cases = [
            (401, MelodyIQAuthenticationError),
            (403, MelodyIQLicenseError),
            (429, MelodyIQRateLimitError),
        ]
        for status, expected_error in cases:
            with self.subTest(status=status):
                session = FakeSession(
                    [
                        FakeResponse(
                            status_code=status,
                            payload={"error": "provider detail"},
                            headers={"Retry-After": "30"},
                        )
                    ]
                )
                client = MelodyIQClient("do-not-leak-this-key", session=session)
                with self.assertRaises(expected_error) as raised:
                    client.get_report("r1")
                self.assertNotIn("do-not-leak-this-key", str(raised.exception))

    def test_impactful_frame_preserves_missing_saves(self):
        frame = impactful_posts_frame(
            [
                {
                    "url": "https://www.tiktok.com/@creator/video/123",
                    "creatorUsername": "creator",
                    "creatorCountry": "SG",
                    "creatorFollowerCount": 100,
                    "viewCount": 1000,
                    "likeCount": 10,
                    "commentCount": 2,
                    "shareCount": 3,
                    "rank": 1,
                }
            ]
        )

        self.assertEqual(frame.loc[0, "Total Engagement"], 15)
        self.assertTrue(pd.isna(frame.loc[0, "Saves"]))
        self.assertEqual(frame.loc[0, "MelodyIQ Impact Rank"], 1)


if __name__ == "__main__":
    unittest.main()
