import unittest
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.modules.setdefault("cv2", SimpleNamespace())

from final_update2_adapter import tag_candidates
from final_update2_backend import load_backend
from model_comparison import (
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
    TARGETED_VERIFIER_MODEL,
    gemini_model_slug,
    normalize_gemini_model,
)


ROOT = Path(__file__).resolve().parents[1]


class ModelComparisonTests(unittest.TestCase):
    def test_supported_models_and_safe_fallback(self):
        self.assertEqual(
            SUPPORTED_GEMINI_MODELS,
            (
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash",
            ),
        )
        self.assertEqual(TARGETED_VERIFIER_MODEL, DEFAULT_GEMINI_MODEL)
        self.assertEqual(normalize_gemini_model("not-a-real-model"), DEFAULT_GEMINI_MODEL)
        self.assertEqual(gemini_model_slug("gemini-3.5-flash"), "gemini_3_5_flash")

    def test_backend_model_context_is_isolated_and_restored(self):
        backend = load_backend()
        self.assertEqual(backend.current_gemini_model(), DEFAULT_GEMINI_MODEL)
        with backend.gemini_model_context("gemini-3.5-flash"):
            self.assertEqual(backend.current_gemini_model(), "gemini-3.5-flash")
        self.assertEqual(backend.current_gemini_model(), DEFAULT_GEMINI_MODEL)

        with backend.gemini_model_context("gemini-3.1-pro-preview"):
            self.assertEqual(backend.current_gemini_model(), DEFAULT_GEMINI_MODEL)
        self.assertEqual(backend.current_gemini_model(), DEFAULT_GEMINI_MODEL)

    def test_approved_flash_models_do_not_add_artificial_sleep(self):
        backend = load_backend()
        with patch.object(backend.time, "sleep") as sleeper:
            for model in SUPPORTED_GEMINI_MODELS:
                with backend.gemini_model_context(model):
                    backend._throttle_gemini_request()
        sleeper.assert_not_called()

    def test_targeted_verifier_stays_on_explicitly_selected_model(self):
        backend = load_backend()
        observed_models = []

        def verifier_call(_prompt, _key):
            observed_models.append(backend.current_gemini_model())
            return {
                "decision": "review",
                "unsupported_labels": [],
                "add_labels": [],
                "confidence": 0.96,
                "evidence": ["The description explicitly presents an on-screen teacher quote."],
                "reason": "Quote presentation is explicit.",
            }

        result = {
            "creative_type": ["Fashion"],
            "narrative": "wise teacher quote",
            "content_details": "A teacher quote is displayed as on-screen text while the creator adjusts her outfit.",
            "confidence": 0.90,
        }
        with backend.gemini_model_context(DEFAULT_GEMINI_MODEL):
            verified = backend.maybe_run_targeted_evidence_verifier(
                result,
                {},
                "key",
                review_reasons=["Attributed quote format is missing the Quotes label"],
                verifier_call=verifier_call,
            )

        self.assertEqual(observed_models, [TARGETED_VERIFIER_MODEL])
        self.assertEqual(verified["_verifier_model"], TARGETED_VERIFIER_MODEL)
        self.assertFalse(verified["_verifier_fallback_used"])
        self.assertEqual(verified["_verifier_status"], "review")

    def test_verifier_uses_robust_json_decoder(self):
        source = (ROOT / "final_update2_backend_source.py").read_text(encoding="utf-8")
        self.assertIn("return _decode_gemini_json(response.text)", source)
        decoded = load_backend()._decode_gemini_json(
            'Result: {"decision":"confirm","unsupported_labels":[],"add_labels":[],"confidence":0.9,"evidence":["clear"],"reason":"ok"}'
        )
        self.assertEqual(decoded["decision"], "confirm")

    def test_adapter_routes_selected_model_and_records_it(self):
        class FakeBackend:
            active_model = DEFAULT_GEMINI_MODEL
            observed_models = []
            context_entries = 0

            @classmethod
            @contextmanager
            def gemini_model_context(cls, model):
                previous = cls.active_model
                cls.active_model = model
                cls.context_entries += 1
                try:
                    yield model
                finally:
                    cls.active_model = previous

            @classmethod
            def run_pipeline(cls, records, *_args, **_kwargs):
                cls.observed_models.append(cls.active_model)
                return pd.DataFrame([
                    {
                        "tiktok_url": record["webVideoUrl"],
                        "Creative Type": "Dance",
                        "Content Details": "A creator performs coordinated hand choreography.",
                        "validation_status": "pass",
                    }
                    for record in records
                ])

        link = "https://www.tiktok.com/@tester/video/7001"
        second_link = "https://www.tiktok.com/@tester/video/7003"
        candidates = pd.DataFrame([
            {"Source": "Comparison", "Market": "KR", "Track": "Test", "Link": link},
            {"Source": "Comparison", "Market": "SG", "Track": "Other", "Link": second_link},
        ])
        records = [
            {"id": "7001", "webVideoUrl": link},
            {"id": "7003", "webVideoUrl": second_link},
        ]
        with patch("final_update2_adapter.load_backend", return_value=FakeBackend()):
            tagged = tag_candidates(
                candidates,
                records,
                "key",
                "token",
                gemini_model="gemini-3.5-flash",
            )

        self.assertEqual(FakeBackend.observed_models, ["gemini-3.5-flash", "gemini-3.5-flash"])
        self.assertEqual(FakeBackend.context_entries, 1)
        self.assertEqual(tagged["Gemini Model"].tolist(), ["gemini-3.5-flash", "gemini-3.5-flash"])
        self.assertTrue(bool(tagged["Gemini Called"].all()))
        self.assertEqual(FakeBackend.active_model, DEFAULT_GEMINI_MODEL)

    def test_every_active_backend_call_reads_context_model(self):
        source = (ROOT / "final_update2_backend_source.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("model=current_gemini_model()"), 4)
        self.assertEqual(source.count("_throttle_gemini_request()"), 5)

    def test_unavailable_row_records_that_gemini_was_not_called(self):
        class FakeBackend:
            @staticmethod
            @contextmanager
            def gemini_model_context(model):
                yield model

            @staticmethod
            def run_pipeline(records, *_args, **_kwargs):
                return pd.DataFrame([{
                    "tiktok_url": records[0]["webVideoUrl"],
                    "Creative Type": "Removed",
                    "tier_used": "auto_removed_unavailable",
                    "review_action": "REMOVE",
                    "validation_status": "removed",
                }])

        link = "https://www.tiktok.com/@tester/video/7002"
        candidates = pd.DataFrame([{"Source": "Comparison", "Market": "PH", "Track": "", "Link": link}])
        records = [{"id": "7002", "webVideoUrl": link}]
        with patch("final_update2_adapter.load_backend", return_value=FakeBackend()):
            tagged = tag_candidates(candidates, records, "key", "token")
        self.assertFalse(bool(tagged.loc[0, "Gemini Called"]))

    def test_ui_and_qa_export_expose_comparison_metadata(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"Analysis model (optional)"', source)
        self.assertNotIn("gemini-3.1-pro-preview", source)
        self.assertIn('"Gemini Model", "Gemini Called", "Comparison Run ID", "Run Started UTC", "Run Elapsed Seconds"', source)
        self.assertIn('f"review_qa_report_{export_model_slug}.xlsx"', source)
        self.assertIn("def reset_review_state_for_new_tagging_run()", source)
        self.assertIn(
            "reset_review_state_for_new_tagging_run()\n                st.session_state.tagged_df = tagged_result",
            source,
        )
        self.assertNotIn('"Continue to Summary without editing"', source)


if __name__ == "__main__":
    unittest.main()
