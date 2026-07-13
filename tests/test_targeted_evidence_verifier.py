import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from evidence_verifier import (
    apply_verifier_response,
    build_verifier_prompt,
    targeted_verifier_reasons,
)


ALLOWED = [
    "Slice of Life", "Lyrics", "Lyrics Translation", "Relationship", "POV",
    "Dance", "Cover", "Lip Sync", "Carousel", "Media/Infotainment",
    "Quotes", "Travel", "Reflection", "Comedy", "Beauty",
    "Movie/Tv/Drama Edits", "Celebrity Edits", "Fitness", "Remix",
    "Fashion", "Gaming", "Others",
]


class TargetedEvidenceVerifierTests(unittest.TestCase):
    def test_strong_missing_fitness_evidence_selects_verifier(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Idol edit",
            "content_details": (
                "A fan montage shows a contestant flexing his muscles and "
                "displaying his physique during a fitness challenge."
            ),
            "confidence": 0.94,
        }
        reasons = targeted_verifier_reasons(result, {}, ALLOWED)
        self.assertIn(
            "Strong Fitness evidence is absent from the selected labels",
            reasons,
        )

    def test_animal_rhythmic_movement_is_dance_evidence(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Cute puppy dance",
            "content_details": (
                "A small dog moves its paws in a rhythmic, dance-like motion "
                "to the music."
            ),
            "confidence": 0.92,
        }
        reasons = targeted_verifier_reasons(result, {}, ALLOWED)
        self.assertIn(
            "Strong Dance evidence is absent from the selected labels",
            reasons,
        )

    def test_clear_relationship_carousel_bypasses_verifier(self):
        result = {
            "creative_type": ["Carousel", "Relationship"],
            "narrative": "Wedding portraits",
            "content_details": "A romantic couple shares wedding photos.",
            "confidence": 0.95,
        }
        row = {
            "url": "https://www.tiktok.com/@tester/photo/123",
            "isSlideshow": True,
            "slideshowImageLinks": ["one", "two", "three"],
        }
        self.assertEqual(targeted_verifier_reasons(result, row, ALLOWED), [])

    def test_unsupported_secondary_dance_is_removed(self):
        result = {
            "creative_type": ["Fashion", "Dance"],
            "narrative": "Outfit showcase",
            "content_details": "A creator poses and walks forward to show a winter outfit.",
            "confidence": 0.94,
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Dance"],
            "add_labels": [],
            "confidence": 0.96,
            "evidence": ["The description only shows posing and an outfit showcase."],
            "reason": "No choreography is described.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["motion conflict"])
        self.assertEqual(output["creative_type"], ["Fashion"])
        self.assertEqual(output["_verifier_status"], "changed")
        self.assertFalse(output.get("needs_human_review", False))

    def test_supported_dance_is_confirmed_without_change(self):
        result = {
            "creative_type": ["Dance", "Lip Sync"],
            "narrative": "Dance performance",
            "content_details": "Two creators perform synchronized choreography while lip-syncing.",
            "confidence": 0.94,
        }
        response = {
            "decision": "confirm",
            "unsupported_labels": [],
            "add_labels": [],
            "confidence": 0.97,
            "evidence": ["Synchronized choreography and lip-syncing are explicit."],
            "reason": "Both labels are directly supported.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["high-confusion pair"])
        self.assertEqual(output["creative_type"], ["Dance", "Lip Sync"])
        self.assertEqual(output["_verifier_status"], "confirmed")

    def test_high_confidence_cannot_confirm_unsupported_dance(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Creator performance",
            "content_details": "A creator faces the camera and poses.",
            "confidence": 0.94,
        }
        response = {
            "decision": "confirm",
            "unsupported_labels": [],
            "add_labels": [],
            "confidence": 0.98,
            "evidence": ["A creator is visible."],
            "reason": "The post is a performance.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["motion conflict"])
        self.assertEqual(output["creative_type"], ["Dance"])
        self.assertEqual(output["_verifier_status"], "review")
        self.assertTrue(output["needs_human_review"])

    def test_unsupported_confirmation_routes_to_review(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Creator performance",
            "content_details": "A creator faces the camera.",
            "confidence": 0.94,
        }
        response = {
            "decision": "confirm",
            "unsupported_labels": [],
            "add_labels": [],
            "confidence": 0.55,
            "evidence": [],
            "reason": "Probably dance.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["motion conflict"])
        self.assertEqual(output["creative_type"], ["Dance"])
        self.assertEqual(output["_verifier_status"], "review")
        self.assertTrue(output["needs_human_review"])

    def test_change_preserves_unrelated_existing_label(self):
        result = {
            "creative_type": ["Relationship", "Dance"],
            "narrative": "Funny relationship moment",
            "content_details": "A romantic couple performs a humorous joke without choreography.",
            "confidence": 0.92,
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Dance"],
            "add_labels": ["Comedy"],
            "confidence": 0.94,
            "evidence": ["The scene is explicitly described as a humorous joke."],
            "reason": "Comedy is supported while Dance is not.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["label conflict"])
        self.assertEqual(output["creative_type"], ["Relationship", "Comedy"])

    def test_low_confidence_change_keeps_labels_and_flags_review(self):
        result = {
            "creative_type": ["Reflection"],
            "narrative": "Emotional message",
            "content_details": "A personal emotional message appears over a road scene.",
            "confidence": 0.93,
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Reflection"],
            "add_labels": ["Lyrics"],
            "confidence": 0.62,
            "evidence": ["Text is visible."],
            "reason": "The text might be lyrics.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["text ambiguity"])
        self.assertEqual(output["creative_type"], ["Reflection"])
        self.assertTrue(output["needs_human_review"])
        self.assertEqual(output["_verifier_status"], "review")

    def test_added_motion_label_requires_explicit_evidence(self):
        result = {
            "creative_type": ["Fashion"],
            "narrative": "Outfit showcase",
            "content_details": "A creator stands still and poses in a new outfit.",
            "confidence": 0.92,
        }
        response = {
            "decision": "change",
            "unsupported_labels": [],
            "add_labels": ["Dance"],
            "confidence": 0.95,
            "evidence": ["The creator moves."],
            "reason": "Possible dance movement.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["motion ambiguity"])
        self.assertEqual(output["creative_type"], ["Fashion"])
        self.assertTrue(output["needs_human_review"])

    def test_verifier_cannot_remove_explicitly_supported_dance(self):
        result = {
            "creative_type": ["Dance", "Travel"],
            "narrative": "Beach dance performance",
            "content_details": "A creator performs synchronized dance choreography on a beach.",
            "confidence": 0.94,
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Dance"],
            "add_labels": [],
            "confidence": 0.99,
            "evidence": ["The beach is the setting."],
            "reason": "Travel is the dominant theme.",
        }
        output = apply_verifier_response(result, response, {}, ALLOWED, ["label conflict"])
        self.assertEqual(output["creative_type"], ["Dance", "Travel"])
        self.assertEqual(output["_verifier_status"], "error")
        self.assertTrue(output["needs_human_review"])

    def test_low_confidence_others_does_not_trigger_text_verifier(self):
        result = {
            "creative_type": ["Others"],
            "narrative": "Unclear post",
            "content_details": "The content cannot be determined.",
            "confidence": 0.40,
        }
        reasons = targeted_verifier_reasons(
            result,
            {},
            ALLOWED,
            review_reasons=["Creative Type is Others", "AI confidence below 80% (40%)"],
        )
        self.assertEqual(reasons, [])

    def test_negated_choreography_does_not_count_as_dance_evidence(self):
        result = {
            "creative_type": ["Fashion"],
            "narrative": "Outfit showcase",
            "content_details": "A creator poses in an outfit without choreography.",
            "confidence": 0.94,
        }
        reasons = targeted_verifier_reasons(result, {}, ALLOWED)
        self.assertNotIn(
            "Strong Dance evidence is absent from the selected labels",
            reasons,
        )

    def test_confirmed_carousel_cannot_be_removed(self):
        result = {
            "creative_type": ["Carousel", "Beauty"],
            "narrative": "Beauty review",
            "content_details": "A photo carousel documents a cosmetic procedure review.",
            "confidence": 0.94,
        }
        row = {
            "url": "https://www.tiktok.com/@tester/photo/123",
            "isSlideshow": True,
            "slideshowImageLinks": ["one", "two"],
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Carousel"],
            "add_labels": [],
            "confidence": 0.98,
            "evidence": ["The content is a beauty review."],
            "reason": "Carousel is only a format.",
        }
        output = apply_verifier_response(result, response, row, ALLOWED, ["format check"])
        self.assertEqual(output["creative_type"], ["Carousel", "Beauty"])
        self.assertTrue(output["needs_human_review"])
        self.assertEqual(output["_verifier_status"], "error")

    def test_string_slideshow_flag_supports_confirmed_carousel(self):
        result = {
            "creative_type": ["Carousel", "Beauty"],
            "narrative": "Beauty review",
            "content_details": "A photo carousel documents a cosmetic procedure review.",
            "confidence": 0.94,
        }
        row = {
            "url": "https://www.tiktok.com/@tester/photo/123",
            "isSlideshow": "true",
            "slideshowImageLinks": ["one", "two"],
        }
        response = {
            "decision": "change",
            "unsupported_labels": ["Carousel"],
            "add_labels": [],
            "confidence": 0.98,
            "evidence": ["The content is a beauty review."],
            "reason": "Carousel is only a format.",
        }
        output = apply_verifier_response(result, response, row, ALLOWED, ["format check"])
        self.assertEqual(output["creative_type"], ["Carousel", "Beauty"])
        self.assertEqual(output["_verifier_status"], "error")

    def test_prompt_requires_review_when_temporal_evidence_is_missing(self):
        prompt = build_verifier_prompt(
            {
                "creative_type": ["Dance"],
                "narrative": "Creator performance",
                "content_details": "A creator faces the camera.",
            },
            {"text": "#fyp"},
            ALLOWED,
            ["Motion evidence is unclear"],
        )
        self.assertIn("choose review instead of guessing", prompt)
        self.assertIn("unsupported_labels", prompt)
        self.assertIn("Motion evidence is unclear", prompt)

    def test_pipeline_calls_verifier_after_temporal_selection(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "final_update2_backend_source.py"
        ).read_text(encoding="utf-8")
        verifier_position = source.index("result = maybe_run_targeted_evidence_verifier(")
        tier_position = source.index("Tier 2C (full video fallback")
        final_review_position = source.index("include_audit=True", verifier_position)
        self.assertGreater(verifier_position, tier_position)
        self.assertLess(verifier_position, final_review_position)


class TargetedVerifierOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        streamlit_stub = SimpleNamespace(
            cache_data=lambda **kwargs: (lambda function: function),
            cache_resource=lambda **kwargs: (lambda function: function),
        )
        sys.modules.setdefault("streamlit", streamlit_stub)
        sys.modules.setdefault("requests", SimpleNamespace())
        sys.modules.setdefault("cv2", SimpleNamespace())
        from final_update2_backend import load_backend

        load_backend.cache_clear()
        cls.backend = load_backend()

    def test_clear_result_does_not_spend_a_verifier_call(self):
        calls = []

        def verifier_call(prompt, key):
            calls.append((prompt, key))
            return {}

        result = {
            "creative_type": ["Carousel", "Relationship"],
            "narrative": "Wedding portraits",
            "content_details": "A romantic couple shares wedding photos.",
            "confidence": 0.95,
        }
        row = {
            "url": "https://www.tiktok.com/@tester/photo/123",
            "isSlideshow": True,
            "slideshowImageLinks": ["one", "two"],
        }
        output = self.backend.maybe_run_targeted_evidence_verifier(
            result, row, "test-key", review_reasons=[], verifier_call=verifier_call
        )
        self.assertEqual(calls, [])
        self.assertEqual(output["creative_type"], ["Carousel", "Relationship"])
        self.assertNotIn("_verifier_status", output)

    def test_triggered_result_runs_once_and_applies_safe_change(self):
        calls = []

        def verifier_call(prompt, key):
            calls.append((prompt, key))
            return {
                "decision": "change",
                "unsupported_labels": ["Dance"],
                "add_labels": [],
                "confidence": 0.94,
                "evidence": ["The creator only poses to display an outfit."],
                "reason": "No choreography is described.",
            }

        result = {
            "creative_type": ["Fashion", "Dance"],
            "narrative": "Outfit showcase",
            "content_details": "A creator only poses to show a winter outfit.",
            "confidence": 0.93,
        }
        output = self.backend.maybe_run_targeted_evidence_verifier(
            result, {}, "test-key", review_reasons=[], verifier_call=verifier_call
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(output["creative_type"], ["Fashion"])
        self.assertEqual(output["_verifier_status"], "changed")

    def test_optional_verifier_outage_fails_open(self):
        result = {
            "creative_type": ["Dance", "Lip Sync"],
            "narrative": "Creator performance",
            "content_details": "A creator performs synchronized choreography while lip-syncing.",
            "confidence": 0.94,
        }
        output = self.backend.maybe_run_targeted_evidence_verifier(
            result,
            {},
            "test-key",
            review_reasons=[],
            verifier_call=lambda prompt, key: {"parse_error": True, "reason": "quota"},
        )
        self.assertEqual(output["creative_type"], ["Dance", "Lip Sync"])
        self.assertEqual(output["_verifier_status"], "error")
        self.assertFalse(output.get("needs_human_review", False))

    def test_changed_labels_are_rechecked_by_post_guardrails(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "final_update2_backend_source.py"
        ).read_text(encoding="utf-8")
        verifier_position = source.index("if verifier_status == 'changed':")
        guardrail_position = source.index("result = apply_post_guardrails(result, row)", verifier_position)
        final_review_position = source.index("include_audit=True", guardrail_position)
        self.assertLess(verifier_position, guardrail_position)
        self.assertLess(guardrail_position, final_review_position)

        guarded = self.backend.apply_post_guardrails(
            {
                "creative_type": ["Beauty", "Carousel"],
                "narrative": "Beauty review",
                "content_details": "A photo carousel documents a cosmetic procedure review.",
                "confidence": 0.94,
            },
            {
                "url": "https://www.tiktok.com/@tester/photo/123",
                "isSlideshow": True,
                "slideshowImageLinks": ["one", "two"],
            },
        )
        self.assertEqual(guarded["creative_type"], ["Carousel", "Beauty"])


if __name__ == "__main__":
    unittest.main()
