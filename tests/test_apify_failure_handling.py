import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

import ugc_tagger.final_update2_adapter as adapter


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


class ApifyApiError(Exception):
    def __init__(self, status_code, message="provider request failed", error_type=""):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.type = error_type


def _load_error_helpers():
    selected_names = {
        "_error_chain_v68_101",
        "_error_texts_v68_101",
        "_apify_error_code_v68_101",
        "_is_quota_interruption_v68_43",
        "_large_batch_must_pause_v68_43",
        "_large_batch_error_code_v68_43",
    }
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    module = ast.Module(
        body=[
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in selected_names
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {
        "BaseException": BaseException,
        "List": List,
        "safe_str": lambda value: "" if value is None else str(value),
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


class ApifyErrorClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_error_helpers()

    def test_structured_apify_status_codes_have_safe_actionable_categories(self):
        classify = self.helpers["_large_batch_error_code_v68_43"]
        self.assertEqual(classify(ApifyApiError(401)), "APIFY_ACCESS")
        self.assertEqual(classify(ApifyApiError(402)), "APIFY_QUOTA")
        self.assertEqual(classify(ApifyApiError(429)), "APIFY_QUOTA")
        self.assertEqual(classify(ApifyApiError(400)), "APIFY_REQUEST")
        self.assertEqual(classify(ApifyApiError(503)), "APIFY_SERVICE")

    def test_wrapped_partial_error_uses_original_provider_status(self):
        provider_error = ApifyApiError(403)
        wrapped = adapter.PartialScrapeError(
            partial_records=[],
            failed_links=["https://www.tiktok.com/@creator/video/123"],
            provider_error=provider_error,
        )
        self.assertEqual(
            self.helpers["_large_batch_error_code_v68_43"](wrapped),
            "APIFY_ACCESS",
        )
        self.assertTrue(self.helpers["_large_batch_must_pause_v68_43"](wrapped))


class PartialScrapeResultTests(unittest.TestCase):
    def test_tiktok_fallback_failure_preserves_direct_records(self):
        direct_link = "https://www.tiktok.com/@direct/video/123"
        fallback_link = "https://www.tiktok.com/@fallback/video/456"
        direct_record = {
            "id": "123",
            "submittedVideoUrl": direct_link,
            "webVideoUrl": direct_link,
            "playCount": 100,
            "diggCount": 10,
            "commentCount": 1,
        }
        provider_error = ApifyApiError(503)
        backend = SimpleNamespace(
            run_apify_tiktok_scraper_api=lambda _links, _token: (_ for _ in ()).throw(
                provider_error
            )
        )

        with patch(
            "ugc_tagger.final_update2_adapter.scrape_tiktok_posts_direct",
            return_value=([direct_record], [fallback_link]),
        ), patch(
            "ugc_tagger.final_update2_adapter.enrich_tiktok_records_with_oembed",
            side_effect=lambda records: records,
        ), patch(
            "ugc_tagger.final_update2_adapter.load_backend",
            return_value=backend,
        ):
            with self.assertRaises(adapter.PartialScrapeError) as raised:
                adapter.scrape_links([direct_link, fallback_link], "token")

        error = raised.exception
        self.assertEqual(error.partial_records, [direct_record])
        self.assertEqual(error.failed_links, [fallback_link])
        self.assertIs(error.provider_error, provider_error)


if __name__ == "__main__":
    unittest.main()
