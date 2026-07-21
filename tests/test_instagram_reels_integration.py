import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from final_update2_adapter import (
    MARKETING_EXPORT_COLUMNS,
    _to_ui_row,
    index_records,
    match_record,
    scrape_links,
)
from final_update2_backend import load_backend
from instagram_reels_adapter import (
    INSTAGRAM_ACTOR_ID,
    INSTAGRAM_REELS,
    TIKTOK,
    detect_platform,
    instagram_shortcode,
    is_instagram_post_url,
    normalize_instagram_record,
    normalize_post_url,
    post_identifier,
    scrape_instagram_posts,
)


VIDEO_URL = "https://www.instagram.com/reel/DExampleAbC1/?utm_source=copy"


class _FakeActor:
    def __init__(self, parent):
        self.parent = parent

    def call(self, *, run_input):
        self.parent.run_input = run_input
        return {"defaultDatasetId": "dataset-1"}


class _FakeDataset:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        return iter(self.items)


class _FakeClient:
    def __init__(self, items):
        self.items = items
        self.actor_id = ""
        self.dataset_id = ""
        self.run_input = {}

    def actor(self, actor_id):
        self.actor_id = actor_id
        return _FakeActor(self)

    def dataset(self, dataset_id):
        self.dataset_id = dataset_id
        return _FakeDataset(self.items)


def instagram_video_record():
    return {
        "id": "3627283333494772362",
        "shortCode": "DExampleAbC1",
        "url": "https://www.instagram.com/reel/DExampleAbC1/",
        "inputUrl": VIDEO_URL,
        "type": "Video",
        "productType": "clips",
        "caption": "A short Reel #dance",
        "likesCount": 250,
        "commentsCount": 12,
        "videoPlayCount": 5000,
        "displayUrl": "https://cdn.example/cover.jpg",
        "videoUrl": "https://cdn.example/video.mp4",
        "videoDuration": 15.5,
        "ownerUsername": "creator_name",
        "ownerFullName": "Creator Name",
        "hashtags": ["dance"],
        "musicInfo": {"song_name": "Test Song", "artist_name": "Test Artist"},
    }


class InstagramUrlTests(unittest.TestCase):
    def test_supported_instagram_paths_and_case_sensitive_shortcode(self):
        self.assertTrue(is_instagram_post_url(VIDEO_URL))
        self.assertTrue(is_instagram_post_url("https://instagram.com/p/AbCdEf123/"))
        self.assertFalse(is_instagram_post_url("https://instagram.com/creator_name/"))
        self.assertEqual(instagram_shortcode(VIDEO_URL), "DExampleAbC1")
        self.assertEqual(post_identifier(VIDEO_URL), "instagram:DExampleAbC1")
        self.assertEqual(detect_platform(VIDEO_URL), INSTAGRAM_REELS)

    def test_normalization_removes_tracking_without_lowercasing_shortcode(self):
        self.assertEqual(
            normalize_post_url(VIDEO_URL),
            "https://www.instagram.com/reel/DExampleAbC1",
        )


class InstagramRecordTests(unittest.TestCase):
    def test_video_record_maps_to_shared_classifier_schema(self):
        record = normalize_instagram_record(instagram_video_record(), VIDEO_URL)
        self.assertEqual(record["_platform"], INSTAGRAM_REELS)
        self.assertEqual(record["text"], "A short Reel #dance")
        self.assertEqual(record["playCount"], 5000)
        self.assertEqual(record["diggCount"], 250)
        self.assertEqual(record["commentCount"], 12)
        self.assertEqual(record["authorMeta"]["name"], "creator_name")
        self.assertEqual(record["musicMeta"]["musicName"], "Test Song")
        self.assertEqual(record["videoMeta"]["originalCoverUrl"], "https://cdn.example/cover.jpg")
        self.assertEqual(record["mediaUrls"], ["https://cdn.example/video.mp4"])
        self.assertFalse(record["isSlideshow"])
        self.assertEqual(record["instagramMetricsUnavailable"], ["Shares", "Saves"])

    def test_sidecar_maps_to_a_confirmed_carousel(self):
        raw = {
            "id": "1",
            "shortCode": "CarouselABC",
            "url": "https://www.instagram.com/p/CarouselABC/",
            "type": "Sidecar",
            "productType": "carousel_container",
            "caption": "Carousel",
            "likesCount": 10,
            "images": ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"],
        }
        record = normalize_instagram_record(raw)
        self.assertTrue(record["isSlideshow"])
        self.assertEqual(len(record["slideshowImageLinks"]), 2)

    def test_adapter_matching_uses_shortcode_across_reel_and_post_paths(self):
        record = normalize_instagram_record(
            {**instagram_video_record(), "url": "https://www.instagram.com/p/DExampleAbC1/"},
            VIDEO_URL,
        )
        by_id, by_url = index_records([record])
        matched = match_record(pd.Series({"Link": VIDEO_URL}), by_id, by_url)
        self.assertIs(matched, record)

    def test_ui_and_export_preserve_platform_and_missing_metric_coverage(self):
        raw = normalize_instagram_record(instagram_video_record(), VIDEO_URL)
        row = _to_ui_row(
            {"Platform": INSTAGRAM_REELS, "Link": VIDEO_URL, "Source": "Pasted links"},
            {
                "tiktok_url": VIDEO_URL,
                "platform": INSTAGRAM_REELS,
                "Creative Type": "Dance",
                "Narrative": "Simple dance",
                "Content Details": "A creator performs a short dance Reel.",
                "plays": 5000,
                "likes": 250,
                "comments": 12,
                "music_name": "Test Song",
                "music_author": "Test Artist",
                "validation_status": "pass",
                "confidence": 0.9,
            },
            raw,
        )
        self.assertEqual(row["App Version"], "v68.42.0")
        self.assertEqual(row["Platform"], INSTAGRAM_REELS)
        self.assertEqual(row["Metrics Unavailable"], "Shares, Saves")
        self.assertEqual(row["Audio From Platform"], "Test Song")
        self.assertEqual(row["Track From TikTok"], "")
        self.assertIn("Platform", MARKETING_EXPORT_COLUMNS)
        self.assertIn("Metrics Unavailable", MARKETING_EXPORT_COLUMNS)


class InstagramScrapeTests(unittest.TestCase):
    def test_actor_call_and_result_order(self):
        client = _FakeClient([instagram_video_record()])
        records = scrape_instagram_posts([VIDEO_URL], "", client=client)
        self.assertEqual(client.actor_id, INSTAGRAM_ACTOR_ID)
        self.assertEqual(client.dataset_id, "dataset-1")
        self.assertEqual(client.run_input["directUrls"], [VIDEO_URL])
        self.assertEqual(client.run_input["resultsType"], "posts")
        self.assertEqual(records[0]["_platform"], INSTAGRAM_REELS)

    def test_missing_actor_result_becomes_auto_removable_error_record(self):
        client = _FakeClient([])
        records = scrape_instagram_posts([VIDEO_URL], "", client=client)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["errorCode"], "POST_NOT_FOUND")
        self.assertEqual(records[0]["submittedVideoUrl"], VIDEO_URL)

    def test_mixed_scrape_routes_each_platform_once(self):
        tiktok_url = "https://www.tiktok.com/@creator/video/7600000000000000001"
        fake_backend = SimpleNamespace(
            run_apify_tiktok_scraper_api=lambda links, token: [
                {"id": "7600000000000000001", "webVideoUrl": links[0]}
            ]
        )
        with patch("final_update2_adapter.load_backend", return_value=fake_backend), patch(
            "final_update2_adapter.scrape_instagram_posts",
            return_value=[normalize_instagram_record(instagram_video_record(), VIDEO_URL)],
        ) as ig_scrape:
            records = scrape_links([tiktok_url, VIDEO_URL], "token")
        self.assertEqual([record["_platform"] for record in records], [TIKTOK, INSTAGRAM_REELS])
        ig_scrape.assert_called_once_with([VIDEO_URL], "token")


class SharedPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("cv2", SimpleNamespace())
        load_backend.cache_clear()
        cls.backend = load_backend()

    def test_tiktok_prompt_keeps_the_frozen_platform_wording(self):
        prompt = self.backend.build_prompt({"_platform": TIKTOK, "text": "test"})
        self.assertIn("You are a senior TikTok UGC content analyst", prompt)
        self.assertIn('Ask: "What type of TikTok content is this?"', prompt)
        self.assertIn("Campaign Market: (not provided) | TikTok-reported Location: (not reported)", prompt)

    def test_instagram_prompt_uses_the_same_taxonomy_with_platform_context(self):
        prompt = self.backend.build_prompt({"_platform": INSTAGRAM_REELS, "text": "test"})
        self.assertIn("You are a senior Instagram Reels UGC content analyst", prompt)
        self.assertIn('Ask: "What type of Instagram Reels content is this?"', prompt)
        self.assertIn("Platform: Instagram Reels", prompt)


if __name__ == "__main__":
    unittest.main()
