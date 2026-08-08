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
        return [{"submittedVideoUrl": link, "id": link.rsplit("/", 1)[-1]} for link in links]


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


if __name__ == "__main__":
    unittest.main()
