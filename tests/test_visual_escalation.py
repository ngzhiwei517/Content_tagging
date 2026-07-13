import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from review_routing import review_risk_reasons, visual_escalation_reasons


VIDEO_ROW = {"url": "https://www.tiktok.com/@tester/video/123"}


class VisualEscalationTests(unittest.TestCase):
    def test_high_confidence_motion_label_still_leaves_cover_tier(self):
        result = {
            "creative_type": ["Lip Sync"],
            "narrative": "Girl lip syncing",
            "content_details": "A creator looks at the camera in a bedroom.",
            "confidence": 0.96,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="cover")
        self.assertTrue(any("Motion-dependent" in reason for reason in reasons))

    def test_creator_performance_is_checked_for_missed_motion_label(self):
        result = {
            "creative_type": ["Comedy"],
            "narrative": "Funny reaction",
            "content_details": "A young woman poses and looks at the camera.",
            "confidence": 0.94,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="cover")
        self.assertTrue(any("Dance or Lip Sync" in reason for reason in reasons))

    def test_negative_reasoning_cannot_suppress_fashion_motion_check(self):
        result = {
            "creative_type": ["Fashion"],
            "narrative": "Outfit showcase",
            "content_details": "A young woman poses and shows off her outfit to the camera.",
            "reasoning": "There is no dancing or lip sync; Fashion was prioritised over unsupported Dance.",
            "confidence": 0.96,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="cover")
        self.assertTrue(any("Dance or Lip Sync" in reason for reason in reasons))

    def test_direct_camera_filter_video_leaves_cover_tier(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Cat filter selfie",
            "content_details": "A young woman looks directly into the camera using a cat-ear filter.",
            "reasoning": "This does not fit into dance or lip-sync categories.",
            "confidence": 0.90,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="cover")
        self.assertTrue(any("Dance or Lip Sync" in reason for reason in reasons))

    def test_full_video_can_resolve_non_motion_creator_performance(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Casual filter selfie",
            "content_details": "A young woman looks directly into the camera using a cat-ear filter.",
            "reasoning": "Full video confirms a static selfie with no performance.",
            "tier_used": "tier2c_full_video",
            "confidence": 0.94,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertFalse(any("Creator performance remains" in reason for reason in reasons))

    def test_photo_carousel_does_not_request_video_frames(self):
        result = {
            "creative_type": ["Carousel", "Quotes"],
            "narrative": "Motivational quote",
            "content_details": "A photo carousel presents a motivational quote.",
            "confidence": 0.93,
        }
        row = {"url": "https://www.tiktok.com/@tester/photo/456", "isSlideshow": True}
        self.assertEqual(visual_escalation_reasons(result, row, stage="cover"), [])

    def test_lyrics_translation_requires_translation_evidence(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Song lyrics",
            "content_details": "Song lyrics appear as text on screen.",
            "confidence": 0.91,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertTrue(any("explicit translation" in reason for reason in reasons))

    def test_explicit_bilingual_lyrics_resolve_translation_ambiguity(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Translated lyrics",
            "content_details": "Original and translated lyrics are shown together as bilingual lyrics.",
            "confidence": 0.91,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertFalse(any("explicit translation" in reason for reason in reasons))

    def test_explicit_animal_dance_resolves_motion_evidence(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Cute puppy dance",
            "content_details": (
                "A small dog moves its paws in a rhythmic, dance-like motion "
                "to the music."
            ),
            "confidence": 0.95,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertFalse(any("Motion label still lacks" in reason for reason in reasons))

    def test_caption_idea_is_not_automatically_infotainment(self):
        result = {
            "creative_type": ["Media/Infotainment"],
            "narrative": "Caption ideas",
            "content_details": "A static post shows caption ideas as overlaid text.",
            "confidence": 0.92,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertTrue(any("informational purpose" in reason for reason in reasons))


class BackendPromptTests(unittest.TestCase):
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

    def test_prompt_explains_lyrics_difference(self):
        prompt = self.backend.build_prompt({})
        self.assertIn("original language", prompt)
        self.assertIn("explicit translation/bilingual evidence", prompt)
        self.assertIn("Ordinary captions, quotes and dialogue subtitles are not Lyrics", prompt)
        self.assertIn("question, viewer prompt or challenge is not POV", prompt)
        self.assertIn("supportive personal message is Reflection", prompt)
        self.assertIn("Animals or animated subjects can be Dance", prompt)

    def test_gym_caption_cannot_turn_visual_fitness_into_dance(self):
        result = {
            "creative_type": ["Fitness"],
            "narrative": "Fitness flex",
            "content_details": "A person flexes their arm muscles and displays their physique in a gym.",
            "reasoning": "The main focus is muscle definition and fitness.",
            "confidence": 0.95,
        }
        row = {
            "text": "SG gyms in a nutshell #gym #fitness",
            "hashtags": [{"name": "gym"}, {"name": "fitness"}],
            "_campaign_market": "SG",
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Fitness"])

    def test_caption_only_dance_cue_cannot_override_visual_fitness(self):
        result = {
            "creative_type": ["Fitness"],
            "narrative": "Fitness flex",
            "content_details": "A bodybuilder flexes their biceps and shows muscle definition.",
            "reasoning": "The post is about physique.",
            "confidence": 0.94,
        }
        row = {
            "text": "gym progress #dance #gym",
            "hashtags": [{"name": "dance"}, {"name": "gym"}],
            "_campaign_market": "SG",
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Fitness"])

    def test_visible_dance_workout_keeps_dance_and_fitness(self):
        result = {
            "creative_type": ["Fitness"],
            "narrative": "Dance workout class",
            "content_details": "A group performs a synchronized dance workout with repeated choreography in a studio.",
            "reasoning": "The class combines exercise with a dance routine.",
            "confidence": 0.93,
        }
        row = {
            "text": "zumba dance workout",
            "hashtags": [{"name": "danceworkout"}, {"name": "fitness"}],
            "_campaign_market": "SG",
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Dance", "Fitness"])

    def test_kb_keyword_context_ignores_guardrail_reasoning(self):
        context = self.backend._kb_context_blob({}, {
            "narrative": "Fitness flex",
            "content_details": "A creator displays muscle definition.",
            "reasoning": "Guardrail: Dance was prioritised.",
        })
        self.assertIn("fitness", context)
        self.assertNotIn("dance", context)

    def test_rejected_dance_word_in_reasoning_cannot_readd_dance(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Translated lyrics",
            "content_details": "A sequence of static aesthetic shots shows translated lyrics.",
            "reasoning": "Visible lyric text was prioritised over Dance.",
            "confidence": 0.90,
        }
        routed = self.backend.apply_vn_v16_remaining_balance_guardrails(
            result, {"_campaign_market": "VN"}
        )
        self.assertNotIn("Dance", routed["creative_type"])

    def test_static_lyrics_safeguard_removes_existing_dance(self):
        result = {
            "creative_type": ["Dance", "Lyrics Translation"],
            "narrative": "Aesthetic traditional outfit",
            "content_details": "A sequence of static aesthetic shots shows the creator with translated lyrics overlaid.",
            "reasoning": "",
            "confidence": 0.90,
        }
        routed = self.backend.apply_static_non_dance_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lyrics Translation"])

    def test_cinematic_couple_montage_becomes_drama_edit(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Romantic couple moments",
            "content_details": "A montage featuring a couple in romantic settings with Vietnamese lyric translations overlaid.",
            "reasoning": "",
            "confidence": 0.90,
        }
        routed = self.backend.apply_vn_v16_remaining_balance_guardrails(
            result, {"_campaign_market": "VN"}
        )
        self.assertEqual(
            routed["creative_type"],
            ["Movie/Tv/Drama Edits", "Lyrics Translation"],
        )

    def test_lyrics_guardrail_preserves_existing_drama_source_label(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Lyrics Translation"],
            "narrative": "Romantic drama montage",
            "content_details": "A drama montage displays bilingual lyrics over cinematic scenes.",
            "reasoning": "The post combines a drama edit with translated lyrics.",
            "confidence": 0.95,
        }
        routed = self.backend.apply_lyrics_guardrails(result, {})
        self.assertEqual(
            routed["creative_type"],
            ["Movie/Tv/Drama Edits", "Lyrics Translation"],
        )

    def test_cinematic_couple_word_order_still_recovers_drama(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Romantic couple moments",
            "content_details": "A romantic montage featuring a couple in intimate cinematic shots with bilingual lyrics.",
            "reasoning": "Translated lyrics are visible.",
            "confidence": 0.95,
        }
        routed = self.backend.apply_vn_v16_remaining_balance_guardrails(
            result, {"_campaign_market": "VN"}
        )
        self.assertEqual(
            routed["creative_type"],
            ["Movie/Tv/Drama Edits", "Lyrics Translation"],
        )

    def test_makeup_transformation_uses_content_details_to_restore_beauty(self):
        result = {
            "creative_type": ["Slice of Life", "Fashion"],
            "narrative": "Makeup transformation",
            "content_details": "A professional makeup artist showcases two makeup and hair styling transformations on a client.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Beauty", "Fashion"])

    def test_distinct_makeup_focus_combines_beauty_with_lip_sync(self):
        result = {
            "creative_type": ["Lip Sync"],
            "narrative": "Girl lip syncing",
            "content_details": "A creator with distinct doll-like makeup looks into the camera and lip-syncs to the music.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lip Sync", "Beauty"])

    def test_ordinary_makeup_does_not_automatically_add_beauty(self):
        result = {
            "creative_type": ["Lip Sync"],
            "narrative": "Girl lip syncing",
            "content_details": "A woman wearing makeup lip-syncs casually while looking at the camera.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lip Sync"])

    def test_direct_to_camera_speech_removes_false_motion_labels(self):
        result = {
            "creative_type": ["Dance", "Lip Sync"],
            "narrative": "Personal announcement",
            "content_details": "A young man talks directly to the camera and expresses his desire to join a team.",
            "reasoning": "",
            "confidence": 0.92,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Others"])
        self.assertTrue(routed["needs_human_review"])

    def test_direct_speech_keeps_existing_non_motion_label(self):
        result = {
            "creative_type": ["Dance", "Reflection"],
            "narrative": "Personal thoughts",
            "content_details": "A creator speaks directly to the camera about personal goals.",
            "reasoning": "",
            "confidence": 0.91,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection"])

    def test_romantic_quote_keeps_quotes_and_adds_relationship(self):
        result = {
            "creative_type": ["Quotes"],
            "narrative": "Relationship quote",
            "content_details": "A static pool shot carries a romantic sentiment about choosing a partner.",
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Relationship", "Quotes"])

    def test_mouthing_details_replace_false_dance_with_lip_sync(self):
        result = {
            "creative_type": ["Dance", "Lyrics Translation"],
            "narrative": "Girl lip syncing",
            "content_details": "A creator is shown mouthing along to song lyrics with their English translations.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lip Sync", "Lyrics Translation"])

    def test_explicit_beach_dance_steps_restore_dance_and_keep_travel(self):
        result = {
            "creative_type": ["Travel"],
            "narrative": "Beach vacation",
            "content_details": (
                "A creator performs rhythmic body movements and dance steps on "
                "a beach at sunset while wearing a patterned swimsuit."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Dance", "Travel"])

    def test_static_beach_pose_does_not_create_dance(self):
        result = {
            "creative_type": ["Travel"],
            "narrative": "Beach vacation",
            "content_details": (
                "A creator poses on a tropical beach at sunset without dancing "
                "or performing choreography."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Travel"])

    def test_confirmed_single_image_removes_carousel(self):
        result = {
            "creative_type": ["Carousel", "Comedy"],
            "narrative": "Cat joke",
            "content_details": "A single image shows two cats with a chemistry joke.",
            "reasoning": "",
            "confidence": 0.95,
        }
        row = {"isSlideshow": True, "slideshowImageLinks": [{"url": "one"}]}
        routed = self.backend.apply_single_image_carousel_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Comedy"])

    def test_confirmed_multi_image_keeps_carousel(self):
        result = {
            "creative_type": ["Carousel", "Relationship"],
            "narrative": "Couple slideshow",
            "content_details": "Four photos show a couple together.",
            "reasoning": "",
            "confidence": 0.95,
        }
        row = {
            "isSlideshow": True,
            "slideshowImageLinks": [{"url": str(index)} for index in range(4)],
        }
        routed = self.backend.apply_single_image_carousel_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Relationship"])

    def test_normal_video_photo_montage_is_not_carousel(self):
        result = {
            "creative_type": ["Carousel", "Lyrics Translation"],
            "narrative": "Traditional portrait montage",
            "content_details": "A normal video presents a series of portrait photos with bilingual lyrics.",
            "reasoning": "",
            "confidence": 0.95,
        }
        row = {"isSlideshow": False, "url": "https://www.tiktok.com/@a/video/123"}
        routed = self.backend.apply_single_image_carousel_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Lyrics Translation"])

    def test_bilingual_language_words_between_bilingual_and_lyrics_are_accepted(self):
        result = {
            "creative_type": ["Lyrics Translation"],
            "narrative": "Translated lyrics",
            "content_details": "Bilingual Vietnamese and Chinese song lyrics are overlaid on screen.",
            "confidence": 0.95,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="frames")
        self.assertFalse(any("explicit translation" in reason for reason in reasons))

    def test_prompt_excludes_carousel_for_one_confirmed_image(self):
        prompt = self.backend.build_prompt(
            {"isSlideshow": True, "slideshowImageLinks": [{"url": "one"}]}
        )
        self.assertIn("Confirmed Slideshow Images: 1", prompt)
        self.assertIn("do NOT use Carousel", prompt)

    def test_review_policy_catches_uncorrected_single_image_carousel(self):
        result = {
            "creative_type": ["Carousel", "Comedy"],
            "narrative": "Cat joke",
            "content_details": "A single image shows two cats with a joke.",
            "confidence": 0.95,
        }
        row = {"isSlideshow": True, "slideshowImageLinks": [{"url": "one"}]}
        reasons = review_risk_reasons(result, row)
        self.assertTrue(any("single-image" in reason for reason in reasons))

    def test_cat_chemistry_joke_is_comedy_not_pov(self):
        result = {
            "creative_type": ["Carousel", "Comedy"],
            "narrative": "Chemistry joke about cats",
            "content_details": "A static image shows two cats with chemical elements used as a humorous pun.",
            "reasoning": "The wordplay is a humorous meme.",
            "confidence": 0.95,
        }
        row = {
            "_campaign_market": "VN",
            "isSlideshow": True,
            "slideshowImageLinks": [{"url": "one"}],
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Comedy"])

    def test_playful_romantic_carousel_keeps_relationship(self):
        result = {
            "creative_type": ["Carousel", "Relationship"],
            "narrative": "Romantic couple moments",
            "content_details": "A slideshow shows a young couple sharing romantic and playful moments outdoors.",
            "reasoning": "The focus is partner dynamics and affection.",
            "confidence": 0.95,
        }
        row = {
            "_campaign_market": "VN",
            "isSlideshow": True,
            "slideshowImageLinks": [{"url": str(index)} for index in range(4)],
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Relationship"])

    def test_wedding_caption_prioritises_relationship_over_lyrics_translation(self):
        result = {
            "creative_type": ["Carousel", "Lyrics Translation"],
            "narrative": "Wedding photoshoot aesthetic",
            "content_details": "A series of aesthetic couple photoshoot portraits with bilingual song lyrics overlaid.",
            "reasoning": "Translated lyrics are visible.",
            "confidence": 0.95,
        }
        row = {
            "text": "Ahhh bộ ảnh cưới chất quá",
            "isSlideshow": True,
            "slideshowImageLinks": [{"url": str(index)} for index in range(4)],
        }
        routed = self.backend.apply_content_details_consistency_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Relationship"])

    def test_review_policy_catches_missing_relationship_from_wedding_caption(self):
        result = {
            "creative_type": ["Carousel", "Lyrics Translation"],
            "narrative": "Wedding photoshoot",
            "content_details": "A couple poses for portraits with translated lyrics.",
            "confidence": 0.95,
        }
        row = {"text": "bộ ảnh cưới", "isSlideshow": True}
        reasons = review_risk_reasons(result, row)
        self.assertTrue(any("Relationship" in reason for reason in reasons))

    def test_cat_closeup_does_not_trigger_creator_performance_escalation(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Cute cat video",
            "content_details": "A close-up of two cats looking at the camera while resting at home.",
            "confidence": 0.94,
        }
        reasons = visual_escalation_reasons(result, VIDEO_ROW, stage="cover")
        self.assertFalse(any("Creator performance" in reason for reason in reasons))

    def test_v66_hamster_cannot_keep_dance(self):
        result = {
            "creative_type": ["Slice of Life", "Dance"],
            "narrative": "Funny hamster",
            "content_details": "A cute hamster rolls around in a container in a humorous manner.",
            "reasoning": "",
            "confidence": 0.92,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Slice of Life", "Comedy"])

    def test_v6813_explicit_animal_dance_is_dance(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Cute puppy dance",
            "content_details": (
                "A small white dog moves its paws in a rhythmic, dance-like "
                "motion to the music."
            ),
            "reasoning": "",
            "confidence": 0.92,
        }
        row = {
            "_campaign_market": "KR",
            "url": "https://www.tiktok.com/@tester/video/321",
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"][0], "Dance")
        reasons = review_risk_reasons(
            routed,
            row,
            include_audit=False,
            include_guardrail_changes=False,
        )
        self.assertFalse(any("Animal Dance" in reason for reason in reasons))

    def test_v66_funny_hamster_adds_comedy_without_false_motion(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Funny hamster",
            "content_details": "A hamster rolls around in a humorous manner.",
            "reasoning": "",
            "confidence": 0.92,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Slice of Life", "Comedy"])

    def test_v66_human_cat_filter_dance_stays_dance(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Cat filter dance",
            "content_details": "A young woman performs hand-focused choreography using cat-themed AR filters.",
            "reasoning": "",
            "confidence": 0.92,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Dance"])

    def test_v66_outfit_movement_is_fashion_not_dance(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Outfit showcase",
            "content_details": "A creator showcases five knitwear outfit combinations while dancing slightly.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Fashion"])

    def test_kr_track_history_cannot_add_dance_to_outfit(self):
        result = {
            "creative_type": ["Fashion"],
            "narrative": "Outfit showcase",
            "content_details": "A creator tries on winter outfit layers and turns to show the clothing.",
            "reasoning": "",
            "confidence": 0.94,
        }
        row = {
            "_campaign_market": "KR",
            "_campaign_track": "BABYMONSTER - Really Like You",
        }
        routed = self.backend.apply_kr_track_dance_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Fashion"])

    def test_v66_lip_sync_without_written_text_removes_lyrics(self):
        result = {
            "creative_type": ["Lip Sync", "Lyrics"],
            "narrative": "Girl lip syncing",
            "content_details": "A creator mouths the song lyrics while facing the camera.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lip Sync"])

    def test_v66_beach_lyrics_adds_travel(self):
        result = {
            "creative_type": ["Lyrics"],
            "narrative": "Beach vacation",
            "content_details": "A woman stands on a tropical beach with song lyrics overlaid on the image.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Travel", "Lyrics"])

    def test_v66_relationship_reflection_adds_reflection(self):
        result = {
            "creative_type": ["Quotes"],
            "narrative": "Relationship reflection",
            "content_details": "Text reflects on the end of a period of being single.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection", "Relationship"])

    def test_v66_spiritual_advice_combines_reflection_and_media(self):
        result = {
            "creative_type": ["Reflection", "Quotes"],
            "narrative": "Emotional spiritual reflection",
            "content_details": "A creator shares a spiritual prayer and personal advice about finding peace during difficult times.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection", "Media/Infotainment"])

    def test_v66_art_tutorial_is_media_not_celebrity(self):
        result = {
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "Art tutorial",
            "content_details": "A step-by-step digital art tutorial rendering an anime character across five images.",
            "reasoning": "",
            "confidence": 0.93,
        }
        row = {"isSlideshow": True, "slideshowImageLinks": [{"url": str(i)} for i in range(5)]}
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Media/Infotainment"])

    def test_v66_cosmetic_review_can_keep_beauty_with_carousel(self):
        result = {
            "creative_type": ["Carousel", "Beauty"],
            "narrative": "Nose surgery review",
            "content_details": "A carousel documents a nose procedure with before-and-after images and a clinic recommendation.",
            "reasoning": "",
            "confidence": 0.93,
        }
        row = {"isSlideshow": True, "slideshowImageLinks": [{"url": str(i)} for i in range(4)]}
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Beauty"])

    def test_v66_abstract_template_requires_review_not_media(self):
        result = {
            "creative_type": ["Media/Infotainment"],
            "narrative": "CapCut template video",
            "content_details": "A rhythmic oscillating abstract graphic animation typical of a CapCut template.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Others"])
        self.assertTrue(routed["needs_human_review"])

    def test_v66_anime_character_is_not_celebrity(self):
        result = {
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "Anime character fan edit",
            "content_details": "A carousel of fan art showing an anime character from Haikyuu.",
            "reasoning": "",
            "confidence": 0.93,
        }
        row = {"isSlideshow": True, "slideshowImageLinks": [{"url": str(i)} for i in range(4)]}
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Movie/Tv/Drama Edits"])

    def test_v66_anime_scene_montage_replaces_generic_reflection(self):
        result = {
            "creative_type": ["Reflection"],
            "narrative": "Jujutsu Kaisen anime edit",
            "content_details": "A montage of scenes from the anime featuring the character Choso and text about brotherhood.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Movie/Tv/Drama Edits"])

    def test_v66_wedding_performance_keeps_relationship(self):
        result = {
            "creative_type": ["Lip Sync", "Dance"],
            "narrative": "Romantic wedding vows",
            "content_details": "A bride performs a synchronized dance routine with her partner in a white suit during a romantic wedding interaction.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Dance", "Relationship"])

    def test_v66_supportive_personal_text_is_reflection_not_lyrics(self):
        result = {
            "creative_type": ["Lyrics", "Slice of Life"],
            "narrative": "Emotional message",
            "content_details": (
                "A quiet road scene has overlaid text expressing care, support, "
                "and reassurance during difficult times."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection", "Slice of Life"])
        self.assertNotIn("Lyrics", routed["creative_type"])

    def test_v66_supportive_song_lyrics_remain_lyrics(self):
        result = {
            "creative_type": ["Lyrics"],
            "narrative": "Supportive song lyrics",
            "content_details": (
                "Visible song lyrics are overlaid on screen as the central content "
                "and express an encouraging message."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Lyrics"])

    def test_v66_humorous_audience_prompt_is_comedy_not_pov(self):
        result = {
            "creative_type": ["POV"],
            "narrative": "Playful audience joke",
            "content_details": (
                "A creator gives an exaggerated humorous reaction while on-screen "
                "text asks viewers to name a flower beginning with a friend's initial."
            ),
            "reasoning": "",
            "confidence": 0.93,
        }
        row = {"text": "Name a flower beginning with a friend's initial"}
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, row)
        self.assertEqual(routed["creative_type"], ["Comedy"])

    def test_v66_explicit_first_person_activity_uses_pov(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Indoor activity diary",
            "content_details": (
                "A first-person perspective follows the creator sliding through "
                "an indoor playground and crossing a rope bridge."
            ),
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["POV", "Slice of Life"])

    def test_v66_ai_generated_fictional_music_performance_is_cover(self):
        result = {
            "creative_type": ["Celebrity Edits", "POV"],
            "narrative": "AI-generated vocal performance",
            "content_details": (
                "An AI-generated fictional child sings into a microphone on a "
                "concert stage while a virtual band performs."
            ),
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Cover"])

    def test_v66_real_celebrity_montage_stays_celebrity(self):
        result = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "Idol fan edit",
            "content_details": (
                "A montage of clips featuring a real K-pop idol at public events "
                "and concert appearances."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_v66_semantic_consistency_guardrail(result, {})
        self.assertEqual(routed["creative_type"], ["Celebrity Edits"])

    def test_makeup_advice_carousel_uses_beauty_not_quotes(self):
        result = {
            "creative_type": ["Carousel", "Quotes"],
            "narrative": "Eye-shape makeup tips",
            "content_details": (
                "A photo carousel advises viewers how to choose eye makeup "
                "looks for different eye shapes."
            ),
            "reasoning": "",
            "confidence": 0.95,
        }
        row = {
            "isSlideshow": True,
            "slideshowImageLinks": ["image-1", "image-2", "image-3"],
        }
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertEqual(routed["creative_type"], ["Carousel", "Beauty"])
        self.assertNotIn("Quotes", routed["creative_type"])

    def test_review_routing_catches_anime_montage_with_generic_label(self):
        result = {
            "creative_type": ["Reflection"],
            "narrative": "Anime edit",
            "content_details": "A montage of scenes from the anime featuring a fictional character.",
            "confidence": 0.95,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertTrue(any("Movie/Tv/Drama Edits" in reason for reason in reasons))

    def test_review_routing_catches_animated_characters_as_generic_lifestyle(self):
        result = {
            "creative_type": ["Slice of Life"],
            "narrative": "Cute winter snow play",
            "content_details": (
                "An animated illustration-style image shows three colorful "
                "fire-like characters building an igloo in a fantasy setting."
            ),
            "confidence": 0.95,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertTrue(any("Movie/Tv/Drama Edits verification" in reason for reason in reasons))

    def test_review_routing_does_not_treat_real_pet_as_fictional_edit(self):
        result = {
            "creative_type": ["Comedy"],
            "narrative": "Funny hamster reaction",
            "content_details": "A real pet hamster rolls in soil inside a plastic container.",
            "confidence": 0.95,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertFalse(any("Movie/Tv/Drama Edits verification" in reason for reason in reasons))

    def test_review_routing_catches_prompt_only_pov(self):
        result = {
            "creative_type": ["POV"],
            "narrative": "Audience flower prompt",
            "content_details": "On-screen text asks viewers to name a flower using a friend's initial.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, {"text": "Name a flower using a friend's initial"})
        self.assertTrue(any("first-person evidence" in reason for reason in reasons))

    def test_review_routing_catches_virtual_singer_without_cover(self):
        result = {
            "creative_type": ["Celebrity Edits", "POV"],
            "narrative": "AI-generated singer",
            "content_details": "An AI-generated fictional child sings into a microphone on stage.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertTrue(any("Cover" in reason for reason in reasons))

    def test_review_routing_catches_makeup_advice_without_beauty(self):
        result = {
            "creative_type": ["Carousel", "Quotes"],
            "narrative": "Eye-shape makeup tips",
            "content_details": "A photo carousel gives makeup advice for different eye shapes.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, {"isSlideshow": True})
        self.assertTrue(any("Beauty" in reason for reason in reasons))

    def test_review_routing_ignores_ordinary_eyeliner(self):
        result = {
            "creative_type": ["Carousel", "Slice of Life"],
            "narrative": "Weekend aesthetic",
            "content_details": "A girl with winged eyeliner poses in a park with a handbag.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, {"isSlideshow": True})
        self.assertFalse(any("Beauty" in reason for reason in reasons))

    def test_review_routing_catches_outfit_labelled_dance(self):
        result = {
            "creative_type": ["Dance"],
            "narrative": "Outfit showcase",
            "content_details": "A creator showcases several knitwear outfit combinations.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertTrue(any("outfit" in reason.lower() or "Dance" in reason for reason in reasons))

    def test_flower_shop_bouquet_does_not_imply_relationship(self):
        result = {
            "creative_type": ["Media/Infotainment"],
            "narrative": "Flower shop showcase",
            "content_details": "A florist presents a large colourful bouquet against a plain background.",
            "reasoning": "A product showcase from a flower shop.",
            "confidence": 0.90,
        }
        row = {"_campaign_market": "VN", "text": "Which bouquet do you like most?"}
        routed = self.backend.apply_post_guardrails(result, row)
        self.assertNotIn("Relationship", routed["creative_type"])

    def test_v67_speech_subtitles_do_not_become_lyrics(self):
        result = {
            "creative_type": ["Lyrics"],
            "narrative": "Team and life goals",
            "content_details": (
                "A man speaks directly to the camera about his team goals. "
                "The on-screen text is subtitles for speech rather than song lyrics."
            ),
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_post_guardrails(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection"])
        self.assertNotIn("Lyrics", routed["creative_type"])

    def test_v67_emotional_introspection_becomes_reflection(self):
        result = {
            "creative_type": ["Lyrics"],
            "narrative": "Emotional introspection",
            "content_details": (
                "A personal emotional introspection about a difficult period; "
                "the text is not a lyric display."
            ),
            "reasoning": "",
            "confidence": 0.94,
        }
        routed = self.backend.apply_post_guardrails(result, {})
        self.assertEqual(routed["creative_type"], ["Reflection"])

    def test_v67_genuine_displayed_song_lyrics_remain_lyrics(self):
        result = {
            "creative_type": ["Lyrics"],
            "narrative": "Lyric video",
            "content_details": "Visible song lyrics are displayed on screen as the central content.",
            "reasoning": "",
            "confidence": 0.95,
        }
        routed = self.backend.apply_post_guardrails(result, {})
        self.assertEqual(routed["creative_type"], ["Lyrics"])

    def test_v67_unsupported_secondary_dance_is_removed(self):
        result = {
            "creative_type": ["Lip Sync", "Dance"],
            "narrative": "Casual lip sync",
            "content_details": (
                "A creator mouths the lyrics while touching her hair and moving "
                "slightly to the beat; no choreography is performed."
            ),
            "reasoning": "",
            "confidence": 0.92,
        }
        routed = self.backend.apply_post_guardrails(result, {})
        self.assertEqual(routed["creative_type"], ["Lip Sync"])

    def test_v67_explicit_choreography_keeps_secondary_dance(self):
        result = {
            "creative_type": ["Lip Sync", "Dance"],
            "narrative": "Dance and lip sync performance",
            "content_details": "Two creators perform a synchronized dance routine while lip syncing.",
            "reasoning": "",
            "confidence": 0.93,
        }
        routed = self.backend.apply_post_guardrails(result, {})
        self.assertEqual(routed["creative_type"], ["Dance", "Lip Sync"])

    def test_v67_review_routes_unsupported_secondary_dance(self):
        result = {
            "creative_type": ["Fashion", "Dance"],
            "narrative": "Outfit showcase",
            "content_details": "A creator poses in a winter outfit and walks toward the camera.",
            "confidence": 0.94,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertIn("Secondary Dance label lacks explicit choreography evidence", reasons)

    def test_v68_15_lip_sync_with_sustained_gestures_is_reviewed(self):
        result = {
            "creative_type": ["Lip Sync"],
            "narrative": "Girl lip syncing",
            "content_details": (
                "A young woman mouths the lyrics while performing various hand "
                "gestures to the song."
            ),
            "confidence": 0.95,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertIn(
            "Lip Sync includes sustained hand/body movement; confirm whether it is Dance choreography",
            reasons,
        )

    def test_v68_15_plain_lip_sync_is_not_forced_to_review(self):
        result = {
            "creative_type": ["Lip Sync"],
            "narrative": "Casual lip sync",
            "content_details": (
                "A young woman mouths the lyrics while seated and uses facial expressions; "
                "her hands remain still."
            ),
            "confidence": 0.95,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertNotIn(
            "Lip Sync includes sustained hand/body movement; confirm whether it is Dance choreography",
            reasons,
        )

    def test_v67_review_routes_comedy_reflection_tone_conflict(self):
        result = {
            "creative_type": ["Reflection"],
            "narrative": "Humorous emotional reflection",
            "content_details": "A funny illustrated joke presents a melancholic personal reflection.",
            "confidence": 0.92,
        }
        reasons = review_risk_reasons(result, VIDEO_ROW)
        self.assertIn("Comedy versus Reflection tone remains ambiguous", reasons)

    def test_pipeline_uses_visual_escalation_and_final_audit(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "final_update2_backend_source.py"
        ).read_text(encoding="utf-8")
        self.assertIn("cover_escalation_reasons", source)
        self.assertIn("frame_refinement_reasons", source)
        self.assertIn("full_video_reasons", source)
        self.assertIn("include_audit=True", source)
        self.assertIn("Normal video requires temporal sampling before final classification", source)
        self.assertIn("audit_only", source)


if __name__ == "__main__":
    unittest.main()
