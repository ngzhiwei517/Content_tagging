import ast
import os
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import requests

from ugc_tagger.direct_post_scraper import scrape_tiktok_posts_direct
from ugc_tagger.final_update2_backend import SOURCE_PATH
from ugc_tagger.final_update2_adapter import (
    _resolved_creator_handle,
    metrics_candidates,
    scrape_links,
)


class _Backend:
    def __init__(self):
        self.links = []

    def run_apify_tiktok_scraper_api(self, links, _token):
        self.links.extend(links)
        return [{
            "submittedVideoUrl": link,
            "id": link.rsplit("/", 1)[-1],
            "playCount": 100,
            "diggCount": 10,
            "commentCount": 1,
        } for link in links]


def _video_info(url):
    post_id = url.rsplit("/", 1)[-1]
    return {
        "id": post_id,
        "webpage_url": url,
        "url": "https://cdn.example/video.mp4",
        "title": "A public TikTok post",
        "uploader_id": "99320625143398400",
        "uploader": "Creator",
        "view_count": 123,
        "like_count": 12,
        "comment_count": 3,
        "save_count": 7,
        "duration": 9,
        "thumbnail": "https://cdn.example/cover.jpg",
        "http_headers": {
            "User-Agent": "public-browser-agent",
            "Referer": "https://www.tiktok.com/",
            "Cookie": "must-not-be-stored",
            "Authorization": "must-not-be-stored",
        },
    }


class DirectPostScraperTests(unittest.TestCase):
    def test_metadata_only_scrape_does_not_create_media_files(self):
        link = "https://www.tiktok.com/@creator/video/123"
        with tempfile.TemporaryDirectory() as folder:
            before = set(os.listdir(folder))
            records, fallback = scrape_tiktok_posts_direct(
                [link], extractor=_video_info
            )
            after = set(os.listdir(folder))

        self.assertEqual(fallback, [])
        self.assertEqual(before, after)
        self.assertEqual(records[0]["_scrape_provider"], "direct_yt_dlp")
        self.assertEqual(records[0]["mediaUrls"], ["https://cdn.example/video.mp4"])
        self.assertEqual(records[0]["videoMeta.downloadAddr"], "https://cdn.example/video.mp4")
        self.assertEqual(records[0]["videoMeta.fallbackDownloadAddr"], link)
        self.assertEqual(records[0]["playCount"], 123)
        self.assertEqual(records[0]["collectCount"], 7)
        self.assertEqual(records[0]["videoMeta.duration"], 9)
        self.assertEqual(records[0]["authorMeta.name"], "creator")
        self.assertEqual(
            records[0]["mediaRequestHeaders"],
            {
                "User-Agent": "public-browser-agent",
                "Referer": "https://www.tiktok.com/",
            },
        )

    def test_numeric_account_id_never_replaces_public_username(self):
        link = "https://www.tiktok.com/@public.handle/video/123"
        records, fallback = scrape_tiktok_posts_direct([link], extractor=_video_info)
        self.assertEqual(fallback, [])
        self.assertEqual(records[0]["authorMeta.name"], "public.handle")

    def test_existing_numeric_creator_is_repaired_from_post_link(self):
        original = {
            "Link": "https://www.tiktok.com/@restored.creator/video/123",
            "Creator": "",
        }
        tagged = {
            "creator_handle": "99320625143398400",
            "creator": "99320625143398400",
        }
        self.assertEqual(
            _resolved_creator_handle(original, tagged),
            "restored.creator",
        )

    def test_photo_and_failed_video_are_returned_for_fallback(self):
        video = "https://www.tiktok.com/@creator/video/123"
        photo = "https://www.tiktok.com/@creator/photo/456"
        records, fallback = scrape_tiktok_posts_direct(
            [video, photo], extractor=lambda _url: None
        )
        self.assertEqual(records, [])
        self.assertEqual(fallback, [video, photo])

    def test_missing_essential_metric_uses_apify_fallback(self):
        link = "https://www.tiktok.com/@creator/video/123"
        for missing_metric in ("view_count", "like_count", "comment_count"):
            with self.subTest(missing_metric=missing_metric):
                incomplete = _video_info(link)
                incomplete.pop(missing_metric)
                records, fallback = scrape_tiktok_posts_direct(
                    [link], extractor=lambda _url, info=incomplete: info
                )
                self.assertEqual(records, [])
                self.assertEqual(fallback, [link])

    def test_explicit_zero_metrics_are_valid_and_do_not_trigger_fallback(self):
        link = "https://www.tiktok.com/@creator/video/123"
        zero_metrics = _video_info(link)
        zero_metrics.update({
            "view_count": 0,
            "like_count": 0,
            "comment_count": 0,
        })

        records, fallback = scrape_tiktok_posts_direct(
            [link], extractor=lambda _url: zero_metrics
        )

        self.assertEqual(fallback, [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["playCount"], 0)
        self.assertEqual(records[0]["diggCount"], 0)
        self.assertEqual(records[0]["commentCount"], 0)

    def test_only_incomplete_post_is_sent_to_fallback(self):
        complete = "https://www.tiktok.com/@creator/video/123"
        incomplete = "https://www.tiktok.com/@creator/video/456"

        def extractor(url):
            info = _video_info(url)
            if url == incomplete:
                info["view_count"] = None
            return info

        records, fallback = scrape_tiktok_posts_direct(
            [complete, incomplete], extractor=extractor
        )

        self.assertEqual([record["submittedVideoUrl"] for record in records], [complete])
        self.assertEqual(fallback, [incomplete])

    def test_adapter_calls_apify_only_for_direct_failures(self):
        direct = "https://www.tiktok.com/@creator/video/123"
        fallback = "https://www.tiktok.com/@creator/video/456"
        backend = _Backend()
        direct_record = _video_info(direct)
        direct_record.update(
            {
                "submittedVideoUrl": direct,
                "webVideoUrl": direct,
                "_platform": "TikTok",
                "platform": "TikTok",
            }
        )
        with patch(
            "ugc_tagger.final_update2_adapter.scrape_tiktok_posts_direct",
            return_value=([direct_record], [fallback]),
        ), patch(
            "ugc_tagger.final_update2_adapter.load_backend",
            return_value=backend,
        ):
            records = scrape_links([direct, fallback], "token")

        self.assertEqual(backend.links, [fallback])
        self.assertEqual(len(records), 2)

    def test_adapter_keeps_available_metrics_from_partial_apify_result(self):
        link = "https://www.tiktok.com/@creator/video/456"
        backend = _Backend()
        backend.run_apify_tiktok_scraper_api = lambda _links, _token: [{
            "submittedVideoUrl": link,
            "id": "456",
            "playCount": 100,
            "diggCount": 10,
        }]
        with patch(
            "ugc_tagger.final_update2_adapter.scrape_tiktok_posts_direct",
            return_value=([], [link]),
        ), patch(
            "ugc_tagger.final_update2_adapter.load_backend",
            return_value=backend,
        ):
            records = scrape_links([link], "token")

        self.assertEqual(len(records), 1)
        refreshed = metrics_candidates(
            pd.DataFrame([{"Platform": "TikTok", "Link": link}]),
            records,
        ).iloc[0]
        self.assertEqual(refreshed["Views"], 100)
        self.assertEqual(refreshed["Likes"], 10)
        self.assertTrue(pd.isna(refreshed["Comments"]))
        self.assertEqual(refreshed["Metrics Status"], "Partial")
        self.assertIn("Comments", refreshed["Metrics Unavailable"])


class DirectMediaReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SOURCE_PATH.read_text(encoding="utf-8")
        selected_names = {
            "get_media_request_headers",
            "is_public_tiktok_post_url",
            "download_video",
        }
        parsed = ast.parse(source, filename=str(SOURCE_PATH))
        module = ast.Module(
            body=[
                node
                for node in parsed.body
                if isinstance(node, ast.FunctionDef) and node.name in selected_names
            ],
            type_ignores=[],
        )
        ast.fix_missing_locations(module)
        namespace = {"os": os, "re": re, "requests": requests}
        exec(compile(module, str(SOURCE_PATH), "exec"), namespace, namespace)
        cls.backend = SimpleNamespace(**namespace)

    def test_flattened_media_headers_are_filtered_case_insensitively(self):
        headers = self.backend.get_media_request_headers({
            "mediaRequestHeaders.user-agent": "browser-agent",
            "mediaRequestHeaders.Referer": "https://www.tiktok.com/",
            "mediaRequestHeaders.Cookie": "must-not-be-used",
            "mediaRequestHeaders.Authorization": "must-not-be-used",
        })
        self.assertEqual(
            headers,
            {
                "User-Agent": "browser-agent",
                "Referer": "https://www.tiktok.com/",
            },
        )

    def test_tiktok_cdn_url_is_downloaded_without_second_yt_dlp_extraction(self):
        response = Mock()
        response.content = b"direct-video"
        response.raise_for_status.return_value = None
        cdn_url = "https://v16-webapp-prime.tiktok.com/video/tos/example.mp4"
        public_url = "https://www.tiktok.com/@creator/video/123"

        with tempfile.TemporaryDirectory() as folder:
            output_path = os.path.join(folder, "video.mp4")
            with patch.object(self.backend.requests, "get", return_value=response) as get:
                result = self.backend.download_video(
                    cdn_url,
                    output_path,
                    "",
                    fallback_url=public_url,
                    request_headers={"Referer": "https://www.tiktok.com/"},
                )
            with open(output_path, "rb") as video:
                saved = video.read()

        self.assertEqual(result, output_path)
        self.assertEqual(saved, b"direct-video")
        get.assert_called_once_with(
            cdn_url,
            headers={"Referer": "https://www.tiktok.com/"},
            timeout=90,
        )

    def test_expired_cdn_url_falls_back_to_public_post(self):
        extracted_urls = []

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, url, download):
                extracted_urls.append((url, download))
                with open(self.options["outtmpl"], "wb") as video:
                    video.write(b"fallback-video")

        cdn_url = "https://v16-webapp-prime.tiktok.com/video/tos/expired.mp4"
        public_url = "https://www.tiktok.com/@creator/video/123"
        fake_module = SimpleNamespace(YoutubeDL=FakeYoutubeDL)

        with tempfile.TemporaryDirectory() as folder:
            output_path = os.path.join(folder, "video.mp4")
            with patch.object(
                self.backend.requests,
                "get",
                side_effect=RuntimeError("expired"),
            ), patch.dict(sys.modules, {"yt_dlp": fake_module}):
                result = self.backend.download_video(
                    cdn_url,
                    output_path,
                    "",
                    fallback_url=public_url,
                )
            with open(output_path, "rb") as video:
                saved = video.read()

        self.assertEqual(result, output_path)
        self.assertEqual(saved, b"fallback-video")
        self.assertEqual(extracted_urls, [(public_url, True)])


if __name__ == "__main__":
    unittest.main()
