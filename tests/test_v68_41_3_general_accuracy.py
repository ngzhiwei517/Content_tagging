import copy
import sys
import unittest
from types import SimpleNamespace

from ugc_tagger.review_routing import review_risk_reasons


class V68413GeneralAccuracyTests(unittest.TestCase):
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

    def route(self, labels, narrative, details, row=None, confidence=0.94):
        result = {
            "creative_type": list(labels),
            "narrative": narrative,
            "content_details": details,
            "confidence": confidence,
            "reasoning": "Initial model decision.",
        }
        return self.backend.apply_post_guardrails(copy.deepcopy(result), row or {})

    def reasons(self, result, row=None):
        return review_risk_reasons(
            result,
            row or {},
            include_audit=False,
            include_guardrail_changes=False,
        )

    def test_rhythmic_hand_choreography_overrides_lip_sync(self):
        routed = self.route(
            ["Lip Sync"],
            "Girl lip syncing",
            "A seated creator mouths song lyrics while performing repeated hand movements in sync with the beat.",
        )
        self.assertEqual(routed["creative_type"][0], "Dance")
        self.assertIn("Lip Sync", routed["creative_type"])

    def test_generic_casual_gestures_stay_lip_sync(self):
        routed = self.route(
            ["Lip Sync"],
            "Casual lip sync",
            "A creator mouths the lyrics in a close-up while making casual hand gestures and touching her hair.",
        )
        self.assertEqual(routed["creative_type"][0], "Lip Sync")
        self.assertNotIn("Dance", routed["creative_type"])

    def test_relationship_can_be_secondary_to_hand_dance(self):
        routed = self.route(
            ["Relationship"],
            "Affectionate couple dance",
            "A couple performs coordinated hand gestures to the music while smiling at each other.",
        )
        self.assertEqual(routed["creative_type"], ["Dance", "Relationship"])

    def test_rhythmic_animal_movement_can_be_dance(self):
        routed = self.route(
            ["Slice of Life"],
            "Aegyo puppy",
            "A puppy wiggles and waves its paws rhythmically to the music in a repeated routine.",
        )
        self.assertEqual(routed["creative_type"][0], "Dance")

    def test_attributed_quote_beats_reflection(self):
        routed = self.route(
            ["Reflection"],
            "Education reflection",
            "Prominent on-screen text presents a quote introduced with 'my teacher once said' while a woman adjusts her hijab.",
        )
        self.assertEqual(routed["creative_type"][0], "Quotes")

    def test_wise_teacher_quote_beats_fashion_even_when_word_order_varies(self):
        routed = self.route(
            ["Fashion"],
            "wise teacher quote",
            "A creator adjusts her headscarf while a quote about simplicity is displayed as on-screen text.",
        )
        self.assertEqual(routed["creative_type"][0], "Quotes")
        self.assertNotIn("Fashion", routed["creative_type"])

    def test_reflective_quote_in_flexible_onscreen_wording_beats_fashion(self):
        routed = self.route(
            ["Fashion"],
            "wise reflection on simplicity",
            "A creator adjusts her hijab while on-screen text shares a reflective quote about knowledge and simplicity.",
        )
        self.assertEqual(routed["creative_type"], ["Quotes"])

    def test_quote_is_not_overwritten_by_ootd_caption(self):
        routed = self.route(
            ["Fashion"],
            "wise reflection on simplicity",
            "A creator adjusts her hijab while on-screen text shares a reflective quote about knowledge and simplicity.",
            {"text": "#ootd #dress #sederhana"},
        )
        self.assertEqual(routed["creative_type"], ["Quotes"])

    def test_funny_personal_anecdote_beats_incidental_lip_sync(self):
        routed = self.route(
            ["Lip Sync"],
            "funny personal anecdote",
            "A creator mouths along while eating and on-screen text shares a funny story about her friends.",
        )
        self.assertEqual(routed["creative_type"], ["Comedy"])

    def test_personal_introspection_is_not_forced_to_quotes(self):
        routed = self.route(
            ["Reflection"],
            "Personal introspection",
            "A creator shares her own thoughts about self-acceptance and healing in a personal reflection.",
        )
        self.assertEqual(routed["creative_type"][0], "Reflection")
        self.assertNotIn("Quotes", routed["creative_type"])

    def test_fit_check_beats_incidental_lip_sync(self):
        routed = self.route(
            ["Lip Sync"],
            "Full black fit check",
            "A woman mouths the audio while presenting a full-black OOTD in a dressing-room mirror outfit check.",
        )
        self.assertEqual(routed["creative_type"][0], "Fashion")
        self.assertIn("Lip Sync", routed["creative_type"])

    def test_false_lyrics_translation_becomes_lip_sync(self):
        routed = self.route(
            ["Lyrics Translation"],
            "Girl lip syncing",
            "A woman mouths song lyrics to the camera; no written lyrics or translation are visible.",
        )
        self.assertEqual(routed["creative_type"][0], "Lip Sync")
        self.assertNotIn("Lyrics Translation", routed["creative_type"])

    def test_genuine_bilingual_lyrics_translation_is_preserved(self):
        routed = self.route(
            ["Lyrics Translation"],
            "Translated lyric card",
            "Original Vietnamese song lyrics and an English translation are visibly displayed together as bilingual lyrics.",
        )
        self.assertIn("Lyrics Translation", routed["creative_type"])

    def test_explicit_drama_edit_matches_narrative(self):
        routed = self.route(
            ["Lyrics Translation"],
            "Romantic drama edit",
            "A fan-made edit features clips from a romantic K-drama with stylized on-screen lyrics.",
        )
        self.assertEqual(routed["creative_type"][0], "Movie/Tv/Drama Edits")
        self.assertNotIn("Lyrics Translation", routed["creative_type"])

    def test_explicit_real_idol_fan_montage_is_celebrity_edit(self):
        routed = self.route(
            ["POV", "Carousel"],
            "K-pop friendship edit",
            "A fan montage compiles clips of two real K-pop idols and public figures.",
        )
        self.assertEqual(routed["creative_type"][0], "Celebrity Edits")

    def test_public_figure_fanfiction_routes_to_adjudication(self):
        result = {
            "creative_type": ["Carousel", "Relationship"],
            "narrative": "Relationship fanfiction",
            "content_details": "A text-based slideshow presents written fanfiction dialogue between fictionalized versions of K-pop idols.",
            "confidence": 0.95,
        }
        reasons = self.reasons(result, {"isSlideshow": True, "slideshowImageLinks": ["1", "2"]})
        self.assertTrue(any("fanfiction versus Celebrity Edits" in reason for reason in reasons))

    def test_public_figure_fanfiction_is_celebrity_edits_when_source_is_explicit(self):
        routed = self.route(
            ["Carousel", "Quotes"],
            "Relationship fanfiction",
            "A 17-slide written fanfiction narrative presents a fictional conversation between real K-pop idols.",
            {"isSlideshow": True, "slideshowImageLinks": ["1", "2"]},
        )
        self.assertEqual(routed["creative_type"], ["Carousel", "Celebrity Edits"])

    def test_literal_visible_pov_text_beats_beauty(self):
        routed = self.route(
            ["Lip Sync", "Beauty"],
            "makeup routine",
            "On-screen text starts with 'POV: doing makeup before the clip' while the creator mouths the audio.",
        )
        self.assertEqual(routed["creative_type"][0], "POV")
        self.assertNotIn("Beauty", routed["creative_type"])

    def test_visible_pov_without_punctuation_beats_beauty(self):
        routed = self.route(
            ["Lip Sync", "Beauty"],
            "makeup routine",
            "On-screen text displays POV followed immediately by a Thai scenario while the creator mouths audio.",
        )
        self.assertEqual(routed["creative_type"][0], "POV")

    def test_sg_cca_post_is_slice_of_life(self):
        routed = self.route(
            ["Carousel", "Reflection"],
            "school frustration",
            "A two-image slideshow shares the relatable Singapore school-life statement 'I hate CCA'.",
            {
                "Market": "SG",
                "url": "https://www.tiktok.com/@tester/photo/123",
                "isSlideshow": True,
                "slideshowImageLinks": ["one", "two"],
            },
        )
        self.assertEqual(routed["creative_type"], ["Carousel", "Slice of Life"])

    def test_school_teacher_quote_remains_quotes(self):
        routed = self.route(
            ["Reflection"],
            "school life lesson",
            "On-screen text presents a teacher quote about learning at school.",
            {"Market": "SG"},
        )
        self.assertEqual(routed["creative_type"][0], "Quotes")

    def test_dance_tutorial_title_without_instruction_does_not_trigger_media_review(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Dance tutorial",
            "content_details": "A seated creator performs coordinated hand choreography in sync with the beat.",
            "confidence": 0.95,
        }
        reasons = self.reasons(result)
        self.assertFalse(any("Media/Infotainment" in reason for reason in reasons))

    def test_dance_and_beauty_do_not_create_false_non_motion_conflict(self):
        result = {
            "creative_type": ["Dance", "Beauty"],
            "narrative": "Hologram makeup transformation",
            "content_details": "A creator performs rhythmic hand choreography during a makeup transformation.",
            "confidence": 0.95,
            "tier_used": "tier2c_full_video",
        }
        reasons = self.backend.visual_escalation_reasons(
            result,
            {},
            stage="full_video",
            previous_result=result,
        )
        self.assertFalse(any("non-motion label" in reason for reason in reasons))

    def test_relationship_dynamics_are_not_hidden_by_structural_guess(self):
        routed = self.route(
            ["Carousel", "POV"],
            "Relationship dynamics",
            "Personal photos show a couple's daily interactions and relationship moments.",
            {"url": "https://www.tiktok.com/@tester/video/123"},
        )
        self.assertEqual(routed["creative_type"][0], "Relationship")

    def test_everyday_scenery_travel_is_routed_to_review(self):
        result = {
            "creative_type": ["Travel"],
            "narrative": "Sunset view",
            "content_details": "A drive along a city highway at sunset shows a double rainbow.",
            "confidence": 0.94,
        }
        reasons = self.reasons(result)
        self.assertTrue(any("trip or destination context" in reason for reason in reasons))

    def test_audience_concert_recording_cover_is_routed_to_review(self):
        result = {
            "creative_type": ["Cover"],
            "narrative": "Live concert performance",
            "content_details": "A fan captures a live artist on stage while the audience cheers and films.",
            "confidence": 0.94,
        }
        reasons = self.reasons(result)
        self.assertTrue(any("audience recording" in reason for reason in reasons))

    def test_explicit_comedy_missing_label_is_routed_to_review(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Snack story",
            "content_details": "A creator tells a funny story using a comedic punchline and exaggerated reaction.",
            "confidence": 0.94,
        }
        reasons = self.reasons(result)
        self.assertTrue(any("Comedy label" in reason for reason in reasons))

    def test_camera_angle_alone_does_not_prove_pov(self):
        result = {
            "creative_type": ["POV"],
            "narrative": "Affectionate note",
            "content_details": "A first-person camera shot captures a hand holding a receipt at a shop counter.",
            "confidence": 0.94,
        }
        reasons = self.reasons(result)
        self.assertTrue(any("camera angle" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
