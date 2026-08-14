import inspect
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ugc_tagger import direct_post_scraper
from ugc_tagger import instagram_reels_adapter


class DirectScraperPerformanceDefaultsTests(unittest.TestCase):
    def _extractor_options(self, extract):
        captured = {}

        class FakeYoutubeDL:
            def __init__(self, options):
                captured.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download):
                self.assert_false(download)
                return {"id": "123"}

            @staticmethod
            def assert_false(value):
                if value:
                    raise AssertionError("Metadata extraction must not download media")

        with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
            extract("https://example.com/post/123")
        return captured

    def test_tiktok_direct_attempt_uses_fast_bounded_defaults(self):
        options = self._extractor_options(direct_post_scraper._default_extract)
        workers = inspect.signature(
            direct_post_scraper.scrape_tiktok_posts_direct
        ).parameters["max_workers"].default

        self.assertEqual(options["socket_timeout"], 12)
        self.assertEqual(options["retries"], 1)
        self.assertEqual(workers, 8)

    def test_instagram_direct_attempt_uses_fast_bounded_defaults(self):
        options = self._extractor_options(
            instagram_reels_adapter._default_direct_instagram_extract
        )
        workers = inspect.signature(
            instagram_reels_adapter.scrape_instagram_posts_direct
        ).parameters["max_workers"].default

        self.assertEqual(options["socket_timeout"], 12)
        self.assertEqual(options["retries"], 1)
        self.assertEqual(workers, 8)


if __name__ == "__main__":
    unittest.main()
