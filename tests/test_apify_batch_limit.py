import unittest
from unittest.mock import patch

from ugc_tagger.final_update2_adapter import (
    MAX_APIFY_POSTS_PER_REQUEST,
    scrape_links,
)


class _Backend:
    def __init__(self):
        self.request_sizes = []

    def run_apify_tiktok_scraper_api(self, links, _token):
        self.request_sizes.append(len(links))
        return [{"submittedVideoUrl": link} for link in links]


class ApifyBatchLimitTests(unittest.TestCase):
    @staticmethod
    def links(count):
        return [
            f"https://www.tiktok.com/@creator/video/{990000 + index}"
            for index in range(count)
        ]

    def test_twenty_five_posts_are_allowed(self):
        backend = _Backend()
        with patch(
            "ugc_tagger.final_update2_adapter.load_backend",
            return_value=backend,
        ):
            records = scrape_links(self.links(MAX_APIFY_POSTS_PER_REQUEST), "token")
        self.assertEqual(backend.request_sizes, [MAX_APIFY_POSTS_PER_REQUEST])
        self.assertEqual(len(records), MAX_APIFY_POSTS_PER_REQUEST)

    def test_twenty_six_posts_are_rejected_before_apify_is_called(self):
        backend = _Backend()
        with patch(
            "ugc_tagger.final_update2_adapter.load_backend",
            return_value=backend,
        ), self.assertRaisesRegex(ValueError, "APIFY_BATCH_LIMIT_EXCEEDED"):
            scrape_links(self.links(MAX_APIFY_POSTS_PER_REQUEST + 1), "token")
        self.assertEqual(backend.request_sizes, [])


if __name__ == "__main__":
    unittest.main()
