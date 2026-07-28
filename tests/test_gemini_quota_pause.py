import sys
import types
import unittest
from unittest.mock import patch

from ugc_tagger.final_update2_backend import load_backend


class _QuotaModels:
    def generate_content(self, **_kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")


class _QuotaClient:
    models = _QuotaModels()


class GeminiQuotaPauseTests(unittest.TestCase):
    def test_gemini_quota_is_raised_as_safe_controlled_exception(self):
        google_module = types.ModuleType("google")
        genai_module = types.ModuleType("google.genai")
        genai_module.Client = lambda api_key: _QuotaClient()
        genai_module.types = types.SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: kwargs
        )
        google_module.genai = genai_module

        with patch.dict(sys.modules, {"cv2": types.ModuleType("cv2")}):
            backend = load_backend()

        with patch.dict(
            sys.modules,
            {
                "google": google_module,
                "google.genai": genai_module,
            },
        ):
            with (
                patch.dict(
                    backend.call_gemini.__globals__,
                    {"GEMINI_BACKOFF_SECONDS": 0},
                ),
                patch.object(backend.random, "randint", return_value=0),
            ):
                with self.assertRaises(backend.GeminiQuotaExhaustedError) as raised:
                    backend.call_gemini(
                        "prompt",
                        "test-key",
                        max_retries=1,
                    )

        self.assertEqual(str(raised.exception), "GEMINI_QUOTA_EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
