import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ugc_tagger.review_routing import review_risk_reasons


class GuardrailHardeningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        streamlit_stub = SimpleNamespace(
            cache_data=lambda **kwargs: (lambda function: function),
            cache_resource=lambda **kwargs: (lambda function: function),
        )
        sys.modules.setdefault("streamlit", streamlit_stub)
        sys.modules.setdefault("requests", SimpleNamespace())
        sys.modules.setdefault("cv2", SimpleNamespace())
        from ugc_tagger.final_update2_backend import load_backend

        load_backend.cache_clear()
        cls.backend = load_backend()

    def test_explicit_market_wins_over_conflicting_country(self):
        row = {"Market": "ID", "Country": "KR", "locationCreated": "US"}
        self.assertEqual(self.backend._kb_extract_market(row), "ID")

    def test_backend_accepts_all_indonesia_aliases(self):
        for alias in ["Indonesia", "Indonesian", "IDN"]:
            with self.subTest(alias=alias):
                self.assertEqual(self.backend._kb_extract_market({"Market": alias}), "ID")

    def test_unsupported_backend_market_stays_blank(self):
        for value in ["Other / no market", "Unknown", "Atlantis", "XX"]:
            with self.subTest(value=value):
                self.assertEqual(self.backend._kb_extract_market({"Market": value}), "")

    def test_false_and_nan_slideshow_flags_do_not_create_carousel(self):
        base = {
            "creative_type": ["Beauty"],
            "narrative": "Makeup review",
            "content_details": "A creator reviews a makeup product in a normal video.",
            "confidence": 0.93,
        }
        kb_hit = {
            "labels": ["Carousel", "Beauty"],
            "narrative": "Beauty carousel",
            "confidence": 0.95,
            "total": 8,
            "source": "test",
        }
        for flag in ["false", "False", False, float("nan")]:
            with self.subTest(flag=flag):
                row = {
                    "url": "https://www.tiktok.com/@tester/video/123",
                    "isSlideshow": flag,
                }
                with patch.object(self.backend, "creative_kb_lookup", return_value=kb_hit):
                    routed = self.backend.apply_knowledge_guardrails(copy.deepcopy(base), row)
                self.assertNotIn("Carousel", routed["creative_type"])

    def test_explicit_photo_preserves_carousel_after_semantic_rule(self):
        result = {
            "creative_type": ["Carousel", "Quotes"],
            "narrative": "Eye-shape makeup advice",
            "content_details": (
                "A photo carousel gives makeup recommendations for different eye shapes."
            ),
            "confidence": 0.94,
        }
        row = {
            "url": "https://www.tiktok.com/@tester/photo/456",
            "isSlideshow": True,
            "slideshowImageLinks": ["one", "two", "three"],
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"][0], "Carousel")
        self.assertIn("Beauty", routed["creative_type"])

    def test_negated_dance_statement_cannot_create_dance(self):
        result = {
            "creative_type": ["Fashion"],
            "narrative": "Outfit showcase",
            "content_details": (
                "The creator models a winter outfit and is not dancing; "
                "there is no choreography or rhythmic movement."
            ),
            "confidence": 0.94,
        }
        row = {"url": "https://www.tiktok.com/@tester/video/789"}
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertNotIn("Dance", routed["creative_type"])
        self.assertIn("Fashion", routed["creative_type"])

    def test_negated_lyrics_statement_cannot_create_lyrics(self):
        result = {
            "creative_type": ["Reflection"],
            "narrative": "Personal reflection",
            "content_details": (
                "Ordinary personal text is shown on screen; it is not lyrics "
                "displayed from a song."
            ),
            "confidence": 0.94,
        }
        row = {"url": "https://www.tiktok.com/@tester/video/790"}
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertNotIn("Lyrics", routed["creative_type"])
        self.assertNotIn("Lyrics Translation", routed["creative_type"])
        self.assertIn("Reflection", routed["creative_type"])

    def test_prompt_separates_campaign_market_from_tiktok_location(self):
        prompt = self.backend.build_prompt({
            "_campaign_market": "ID",
            "Market": "ID",
            "locationCreated": "US",
        })
        self.assertIn("Campaign Market: ID", prompt)
        self.assertIn("TikTok-reported Location: US", prompt)
        self.assertNotIn("| Market: US", prompt)

    def test_id_uses_generic_guardrails_and_review_routing(self):
        base = {
            "creative_type": ["Fashion"],
            "narrative": "Winter outfit showcase",
            "content_details": (
                "A creator models a winter outfit without choreography or rhythmic movement."
            ),
            "confidence": 0.94,
        }
        blank_row = {"url": "https://www.tiktok.com/@tester/video/791", "Market": ""}
        id_row = {"url": "https://www.tiktok.com/@tester/video/791", "Market": "ID"}
        with patch.object(
            self.backend,
            "creative_kb_lookup",
            return_value={"labels": [], "confidence": 0.0, "total": 0},
        ):
            blank_result = self.backend.apply_post_guardrails(copy.deepcopy(base), blank_row)
            id_result = self.backend.apply_post_guardrails(copy.deepcopy(base), id_row)

        self.assertEqual(id_result["creative_type"], blank_result["creative_type"])
        id_reasons = review_risk_reasons(
            id_result,
            id_row,
            include_audit=False,
            include_guardrail_changes=False,
        )
        blank_reasons = review_risk_reasons(
            blank_result,
            blank_row,
            include_audit=False,
            include_guardrail_changes=False,
        )
        self.assertEqual(id_reasons, blank_reasons)
        combined_reasoning = " ".join([
            str(id_result.get("reasoning", "")),
            *map(str, id_reasons),
        ]).lower()
        self.assertNotIn("indonesia guardrail", combined_reasoning)
        self.assertNotIn("id guardrail", combined_reasoning)


if __name__ == "__main__":
    unittest.main()
