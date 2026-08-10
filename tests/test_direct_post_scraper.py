import os
import tempfile
import unittest
from unittest.mock import patch

from ugc_tagger.direct_post_scraper import scrape_tiktok_posts_direct
from ugc_tagger.final_update2_adapter import _resolved_creator_handle, scrape_links


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
        self.assertEqual(records[0]["mediaUrls"], [link])
        self.assertEqual(records[0]["playCount"], 123)
        self.assertEqual(records[0]["collectCount"], 7)
        self.assertEqual(records[0]["videoMeta.duration"], 9)
        self.assertEqual(records[0]["authorMeta.name"], "creator")

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

    def test_adapter_rejects_incomplete_apify_metrics(self):
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

        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
