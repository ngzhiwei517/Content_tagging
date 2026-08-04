import sys
import types
import unittest
from unittest.mock import patch

from ugc_tagger.final_update2_backend import load_backend


class _QuotaModels:
    calls = 0

    def generate_content(self, **_kwargs):
        type(self).calls += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")


class _QuotaClient:
    models = _QuotaModels()


class GeminiQuotaPauseTests(unittest.TestCase):
    def test_gemini_quota_is_raised_as_safe_controlled_exception(self):
        _QuotaModels.calls = 0
        google_module = types.ModuleType("google")
        genai_module = types.ModuleType("google.genai")
        genai_module.Client = lambda **_kwargs: _QuotaClient()
        genai_module.types = types.SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: kwargs,
            HttpOptions=lambda **kwargs: kwargs,
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
            with patch.object(backend.time, "sleep") as mocked_sleep:
                with self.assertRaises(backend.GeminiQuotaExhaustedError) as raised:
                    backend.call_gemini(
                        "prompt",
                        "test-key",
                        max_retries=3,
                    )

        self.assertEqual(str(raised.exception), "GEMINI_QUOTA_EXHAUSTED")
        self.assertEqual(_QuotaModels.calls, 1)
        mocked_sleep.assert_not_called()

    def test_gemini_client_uses_a_bounded_request_timeout(self):
        captured = {}

        class SuccessModels:
            def generate_content(self, **_kwargs):
                return types.SimpleNamespace(text='{}')

        class SuccessClient:
            models = SuccessModels()

        google_module = types.ModuleType("google")
        genai_module = types.ModuleType("google.genai")

        def client_factory(**kwargs):
            captured.update(kwargs)
            return SuccessClient()

        genai_module.Client = client_factory
        genai_module.types = types.SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: kwargs,
            HttpOptions=lambda **kwargs: kwargs,
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
            backend.call_gemini("prompt", "test-key", max_retries=1)

        self.assertEqual(
            captured["http_options"]["timeout"],
            backend.GEMINI_REQUEST_TIMEOUT_MS,
        )
        self.assertEqual(backend.GEMINI_REQUEST_TIMEOUT_MS, 60_000)


if __name__ == "__main__":
    unittest.main()
