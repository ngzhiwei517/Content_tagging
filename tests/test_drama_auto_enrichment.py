import unittest
from pathlib import Path
from unittest.mock import patch

from ugc_tagger.drama_analysis import (
    DRAMA_EXPORT_COLUMNS,
    DRAMA_REVIEW_OPTIONS,
    apply_audio_comparison,
    apply_generic_original_audio_default,
    apply_drama_enrichment,
    build_drama_prompt,
    build_review_drama_updates,
    campaign_track_catalog_status,
    clear_itunes_preview_cache,
    drama_review_defaults,
    drama_export_values,
    fetch_itunes_preview,
    has_drama_label,
    promote_entertainment_news_label,
    resolve_audio_fields,
    route_thailand_carousel_ambiguity_to_review,
    route_unknown_drama_audio_to_review,
    split_campaign_track,
)
from ugc_tagger.final_update2_adapter import MARKETING_EXPORT_COLUMNS


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _itunes_get(*_args, **_kwargs):
    return _Response({
        "results": [{
            "trackName": "Example Song",
            "artistName": "Example Artist",
            "previewUrl": "https://example.test/preview.m4a",
            "trackViewUrl": "https://example.test/song",
        }]
    })


class DramaAutoEnrichmentTests(unittest.TestCase):
    def tearDown(self):
        clear_itunes_preview_cache()

    def test_apple_catalogue_lookup_is_cached_once_per_normalized_track(self):
        calls = []

        def counted_get(*args, **kwargs):
            calls.append((args, kwargs))
            return _itunes_get(*args, **kwargs)

        clear_itunes_preview_cache()
        with patch("requests.get", side_effect=counted_get):
            first = fetch_itunes_preview("Example Song")
            second = fetch_itunes_preview("  example   song  ")

        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    def test_failed_apple_catalogue_lookup_is_not_cached(self):
        calls = []

        def empty_get(*_args, **_kwargs):
            calls.append(True)
            return _Response({"results": []})

        clear_itunes_preview_cache()
        with patch("requests.get", side_effect=empty_get):
            self.assertEqual(fetch_itunes_preview("Missing Example Song"), {})
            self.assertEqual(fetch_itunes_preview("Missing Example Song"), {})

        self.assertEqual(len(calls), 2)

    def test_review_format_options_only_expose_long_form_and_short_form_drama(self):
        self.assertEqual(
            DRAMA_REVIEW_OPTIONS["drama_format"],
            ("Long-form Drama", "Short-form Drama"),
        )

    def test_only_exact_broad_drama_label_triggers(self):
        self.assertTrue(has_drama_label(["Movie/Tv/Drama Edits", "Relationship"]))
        self.assertFalse(has_drama_label(["Celebrity Edits"]))
        self.assertFalse(has_drama_label(["Drama-like lifestyle"]))

    def test_non_drama_result_is_unchanged(self):
        original = {
            "creative_type": ["Dance"],
            "content_details": "A creator performs choreography.",
        }
        self.assertEqual(apply_drama_enrichment(original, {}, {}), original)

    def test_structured_details_are_one_field_per_line(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Two fictional characters share an emotional scene.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Long-form Drama",
            "country_region": "Thailand",
            "drama_title": "Example Series",
            "detected_audio": "Unknown",
            "campaign_song_match": "Unknown",
            "audio_version": "Unknown",
            "visual_summary": "Two fictional male characters share an emotional scene.",
            "evidence": ["fictional dialogue scene", "recurring characters"],
            "review_reason": "",
        }
        enriched = apply_drama_enrichment(result, response, {})
        details = enriched["content_details"]
        expected_headers = [
            "Visual Summary:", "Content Category:", "Drama Type:", "Edit Focus:", "Format:",
            "Country/Region:", "Drama Title:", "Detected Audio:",
            "Audio Version:",
        ]
        self.assertEqual(len(details.splitlines()), len(expected_headers))
        for header in expected_headers:
            self.assertIn(header, details)

    def test_cp_requires_real_actor_evidence(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A fictional episode scene.",
        }
        response = {
            "content_categories": ["CP Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "drama_format": "Scene Compilation",
            "country_region": "Thailand",
            "drama_title": "Unknown",
            "evidence": ["fictional characters in an episode scene"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["edit_focus"], "Fictional Story")
        self.assertIn("lacked real-actor", enriched["drama_review_reason"])

    def test_real_actor_fanmeet_keeps_bl_cp(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Two male actors from a BL series interact at an event.",
        }
        response = {
            "content_categories": ["CP Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "drama_format": "Fan Edit",
            "country_region": "Thailand",
            "drama_title": "Unknown",
            "evidence": ["two male BL actors at a fanmeet", "off-screen interaction"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["edit_focus"], "BL CP Edit")
        self.assertEqual(enriched["drama_format"], "Not applicable")

    def test_unsupported_bl_cp_is_replaced_and_kept_for_review(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Relationship"],
            "narrative": "Romantic couple moments",
            "content_details": "A romantic montage featuring a couple singing together.",
        }
        response = {
            "content_categories": ["CP Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "drama_format": "Unknown",
            "country_region": "China",
            "drama_title": "Unknown",
            "detected_audio": "漫步香港1999",
            "visual_summary": (
                "A romantic edit featuring Vietnamese celebrities Hai Dang Doo "
                "and Lamoon, focusing on their close chemistry."
            ),
            "evidence": [],
        }
        row = {
            "_campaign_track": "xingying - 【漫步香港1999】| Wandering in Hong Kong",
            "musicMeta": {"musicName": "nhạc nền - 🐽", "musicAuthor": "🐽"},
        }

        def no_itunes(*_args, **_kwargs):
            return _Response({"results": []})

        enriched = apply_drama_enrichment(result, response, row, http_get=no_itunes)
        self.assertEqual(enriched["drama_type"], "General Drama")
        self.assertEqual(enriched["edit_focus"], "Cast/Actor Edit")
        self.assertEqual(enriched["country_region"], "Vietnam")
        self.assertEqual(enriched["detected_audio"], "漫步香港1999")
        self.assertTrue(enriched["needs_human_review"])
        self.assertIn("lacked explicit same-gender", enriched["drama_review_reason"])

    def test_supported_bl_is_not_downgraded_by_a_woman_in_the_wider_cast(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Two male BL leads share a romantic moment while a female host watches.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "Fictional Story",
            "country_region": "Thailand",
            "visual_summary": "Two male romantic leads appear with a woman from the wider cast.",
            "evidence": ["two male BL leads", "fictional scene"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["drama_type"], "BL Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")

    def test_entertainment_news_omits_drama_only_fields(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A creator compares two actors.",
        }
        response = {
            "content_categories": ["Entertainment News", "Actor/Actress Carousel"],
            "drama_type": "General Drama",
            "edit_focus": "Cast/Actor Edit",
            "drama_format": "Long-form Drama",
            "country_region": "China",
            "drama_title": "A Splendid Match",
            "visual_summary": "A creator compares two actors and their mannerisms.",
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Entertainment News", "Actor/Actress Carousel"])
        self.assertEqual(enriched["drama_format"], "Not applicable")
        self.assertEqual(drama_export_values(enriched)["Drama Format"], "")
        self.assertIn("Content Category: Entertainment News, Actor/Actress Carousel", enriched["content_details"])
        self.assertNotIn("Drama Type:", enriched["content_details"])
        self.assertNotIn("Format:", enriched["content_details"])
        self.assertNotIn("Drama Title:", enriched["content_details"])

    def test_actor_press_interview_overrides_model_drama_edit(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Drama ending discussion",
            "content_details": "Actor Ren Jialun discusses the ending of a television drama.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Character Edit",
            "drama_format": "Long-form Drama",
            "country_region": "China",
            "drama_title": "Unknown",
            "visual_summary": "A real actor answers an interviewer while holding a branded microphone.",
            "evidence": ["press interview", "the actor comments on the open ending"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Entertainment News"])
        self.assertEqual(enriched["drama_type"], "Unknown")
        self.assertEqual(enriched["edit_focus"], "Unknown")
        self.assertEqual(enriched["drama_format"], "Not applicable")
        self.assertNotIn("Drama Type:", enriched["content_details"])
        self.assertNotIn("Format:", enriched["content_details"])

    def test_actor_meta_discussion_overrides_drama_edit_even_with_drama_broll(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Drama ending discussion",
            "content_details": "An actor discusses his character and the drama ending.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "visual_summary": "An actor interview is intercut with illustrative scenes from the series.",
            "evidence": ["The actor shares his thoughts about the ending."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Entertainment News"])

    def test_fictional_scene_montage_remains_drama_edit(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Tragic final episode montage",
            "content_details": "A montage of fictional scenes showing the character's tragic ending.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Long-form Drama",
            "visual_summary": "Recurring fictional characters appear in emotional storyline scenes.",
            "evidence": ["episode scenes", "fictional plot montage"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertEqual(enriched["drama_type"], "General Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")
        self.assertEqual(enriched["drama_format"], "Long-form Drama")

    def test_historical_cdrama_scene_montage_overrides_news_suggestion(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": (
                "A montage of clips from a historical Chinese drama, focusing "
                "on supportive romantic gestures between the characters."
            ),
        }
        response = {
            "content_categories": ["Entertainment News"],
            "country_region": "China",
            "visual_summary": (
                "A montage featuring actors in a historical Chinese drama, "
                "showing fictional scenes between the two leads."
            ),
            "evidence": ["Recurring characters appear in scripted drama scenes."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertEqual(enriched["drama_type"], "General Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")

    def test_named_drama_emotional_scene_montage_overrides_news_suggestion(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": (
                "An emotional montage of scenes from the Chinese drama Make a "
                "Wish, highlighting romantic tension between characters."
            ),
        }
        response = {
            "content_categories": ["Entertainment News"],
            "country_region": "China",
            "drama_title": "Make a Wish",
            "visual_summary": (
                "A montage of fictional story scenes with a protective, tearful "
                "interaction between the leads."
            ),
            "evidence": ["The same fictional characters recur across episode scenes."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertEqual(enriched["drama_type"], "General Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")

    def test_pelarian_fictional_interaction_overrides_news_suggestion(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": (
                "A montage depicting an emotional interaction between a man "
                "in a suit and a woman, featuring text message communication."
            ),
        }
        response = {
            "content_categories": ["Entertainment News"],
            "country_region": "China",
            "visual_summary": result["content_details"],
            "detected_audio": "Pelarian",
            "audio_version": "Original",
        }
        enriched = apply_drama_enrichment(result, response, {"Track": "Pelarian"})
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertEqual(enriched["drama_type"], "General Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")

    def test_actor_reflection_on_character_remains_entertainment_news(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Actor reflects on emotional drama character",
            "content_details": (
                "Actor Ding Yu Xi shares his emotional experience reflecting on "
                "his character's tragic fate."
            ),
        }
        response = {
            "content_categories": ["Drama Edit"],
            "country_region": "China",
            "visual_summary": (
                "A real actor reflects on his role and performance while speaking "
                "to the audience."
            ),
            "evidence": ["The actor discusses his character rather than acting a scene."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Entertainment News"])

    def test_livestream_wellbeing_update_routes_celebrity_edit_to_news(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "Idol concern update",
            "content_details": (
                "A fan-created collage shows Chinese actors during livestream "
                "interactions and expresses concern for the actor's well-being."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Entertainment News",
        )

    def test_ordinary_livestream_fan_montage_stays_celebrity_edit(self):
        original = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "Idol fan montage",
            "content_details": (
                "A fan-created montage of an actor smiling during several "
                "livestream interactions."
            ),
        }
        self.assertEqual(promote_entertainment_news_label(original), original)

    def test_caption_only_interview_word_does_not_override_fictional_visuals(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Fictional courtroom scene",
            "content_details": "Two characters argue during a scripted television episode.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "visual_summary": "Only fictional scenes and recurring characters are shown.",
            "evidence": ["scripted episode scene", "no host or press setting"],
        }
        row = {"text": "Actor interview #cdrama", "hashtags": [{"name": "interview"}]}
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])

    def test_anime_is_not_general_drama(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "An anime character montage.",
        }
        response = {
            "content_categories": ["Anime Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Character Edit",
            "drama_format": "Short-form Drama",
            "country_region": "Japan",
            "drama_title": "Re:Zero",
            "visual_summary": "An anime montage focused on Subaru.",
            "evidence": ["anime series scenes", "Subaru is the central character"],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Anime Edit"])
        self.assertEqual(enriched["drama_type"], "Unknown")
        self.assertEqual(enriched["drama_format"], "Not applicable")
        self.assertIn("Anime Title: Re:Zero", enriched["content_details"])
        self.assertNotIn("General Drama", enriched["content_details"])

    def test_live_action_soap_opera_overrides_wrong_anime_suggestion(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": "A live-action man and woman appear in an Indonesian soap opera.",
        }
        response = {
            "content_categories": ["Anime Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Indonesia",
            "drama_title": "Unknown",
            "visual_summary": "A montage of a real male and female lead in an Indonesian soap opera.",
            "evidence": ["filmed actors", "live-action romantic scenes"],
        }
        row = {"text": "local drama #anime", "hashtags": [{"name": "anime"}]}
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertNotIn("Anime Title:", enriched["content_details"])
        self.assertTrue(enriched["needs_human_review"])
        self.assertIn("Anime suggestion contradicted", enriched["review_risk_reasons"])

    def test_negated_anime_evidence_does_not_trigger_anime(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A live-action soap opera scene.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "visual_summary": "Real actors perform a scripted television drama scene.",
            "evidence": ["This is not anime; it is filmed with human actors."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])

    def test_explicit_caption_title_recovers_unknown_model_title(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A live-action drama montage.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_title": "Unknown",
            "visual_summary": "A montage from a television drama.",
        }
        row = {"text": "Drama title: A Splendid Match #cdrama"}
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["drama_title"], "A Splendid Match")
        self.assertIn("Drama Title: A Splendid Match", enriched["content_details"])

    def test_generic_hashtags_do_not_become_drama_title(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A live-action drama montage.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_title": "Unknown",
            "visual_summary": "A montage from a television drama.",
        }
        row = {
            "text": "Romantic edit #cdrama #fyp #actorname",
            "hashtags": [{"name": "cdrama"}, {"name": "fyp"}, {"name": "actorname"}],
        }
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["drama_title"], "Unknown")

    def test_editorial_celebrity_post_is_promoted_for_detailed_routing(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Fashion", "Celebrity Edits"],
            "narrative": "celebrity fashion showcase",
            "content_details": "An actress appears in a fashion magazine editorial.",
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertIn("Fashion", promoted["creative_type"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "Entertainment News")

    def test_celebrity_banter_update_routes_to_entertainment_news(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "Celebrity banter and interaction",
            "content_details": (
                "A commentary update about Chinese celebrities sharing funny "
                "banter during a public appearance."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "Entertainment News")

    def test_celebrity_child_update_is_news_not_profile_carousel(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "celebrity child update",
            "content_details": (
                "A split-screen image reports an update about an actress and "
                "her daughter becoming a presenter."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "Entertainment News")

    def test_kpop_interview_banter_routes_to_kpop_show_cut(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits", "Comedy"],
            "narrative": "BIGBANG members funny banter",
            "content_details": (
                "BIGBANG members share humorous reactions and dialogue during "
                "an interview with on-screen subtitles."
            ),
        })
        self.assertEqual(
            promoted["creative_type"],
            ["Movie/Tv/Drama Edits", "Comedy"],
        )
        self.assertEqual(promoted["_drama_content_kind_hint"], "K-pop Show Cut")

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Entertainment News"],
            "country_region": "Korea",
            "visual_summary": "BIGBANG members exchange jokes during an interview.",
        })
        self.assertEqual(enriched["content_categories"][0], "K-pop Show Cut")
        self.assertIn("Content Category: K-pop Show Cut", enriched["content_details"])

    def test_kpop_interview_montage_removes_incidental_dance(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Dance", "Celebrity Edits"],
            "narrative": "K-pop idol challenge culture",
            "content_details": (
                "A montage featuring interviews with K-pop idols discussing "
                "their participation in dance challenges, interspersed with "
                "clips of choreography."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "K-pop Show Cut")

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Entertainment News"],
            "country_region": "Korea",
            "visual_summary": "BIGBANG members discuss dance challenges in interviews.",
        })
        self.assertEqual(enriched["content_categories"], ["K-pop Show Cut"])
        self.assertIn("Content Category: K-pop Show Cut", enriched["content_details"])

    def test_kpop_music_video_brainstorm_segment_routes_to_show_cut(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits", "Comedy"],
            "narrative": "Big Bang reunion antics",
            "content_details": (
                "Members of Big Bang brainstorm creative ideas for a music "
                "video before a playful music sequence."
            ),
        })
        self.assertEqual(
            promoted["creative_type"],
            ["Movie/Tv/Drama Edits", "Comedy"],
        )
        self.assertEqual(promoted["_drama_content_kind_hint"], "K-pop Show Cut")

    def test_kpop_studio_collaboration_segment_routes_to_show_cut(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Dance", "Celebrity Edits"],
            "narrative": "Idol interaction and collaboration",
            "content_details": (
                "K-pop idols interact in a recording studio and collaborate to "
                "complete a puzzle during a behind-the-scenes segment."
            ),
        })
        self.assertEqual(
            promoted["creative_type"],
            ["Dance", "Movie/Tv/Drama Edits"],
        )
        self.assertEqual(promoted["_drama_content_kind_hint"], "K-pop Show Cut")

    def test_ordinary_kpop_fan_montage_stays_celebrity_edit(self):
        original = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "BIGBANG idol fan montage",
            "content_details": "A fast montage of stage and promotional photos.",
        }
        self.assertEqual(promote_entertainment_news_label(original), original)

    def test_real_celebrity_romantic_pair_routes_to_cp_and_preserves_lyrics(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits", "Lyrics"],
            "narrative": "romantic idol couple interaction",
            "content_details": (
                "A montage featuring two Thai celebrities interacting "
                "affectionately and playfully while lounging together."
            ),
        })
        self.assertEqual(
            promoted["creative_type"],
            ["Movie/Tv/Drama Edits", "Lyrics"],
        )
        self.assertEqual(promoted["_drama_content_kind_hint"], "CP Edit")

    def test_explicit_two_male_real_celebrity_pair_resolves_to_bl_cp(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits", "Lyrics"],
            "narrative": "romantic idol couple interaction",
            "content_details": (
                "Two male Thai celebrities interact affectionately in an "
                "off-screen couch montage."
            ),
        })
        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Drama Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Thailand",
            "visual_summary": (
                "Two male celebrities share playful romantic chemistry "
                "while lounging together off-screen."
            ),
            "evidence": ["two male celebrities", "affectionate chemistry"],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "BL Drama")
        self.assertEqual(enriched["edit_focus"], "BL CP Edit")

    def test_explicit_two_female_actress_pair_resolves_to_gl_cp(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Relationship"],
            "narrative": "romantic off-screen actress chemistry",
            "content_details": (
                "Two female Thai actresses interact affectionately and make "
                "heart gestures together."
            ),
        }, {
            "text": "A sweet pair moment #glseries #foumbam",
            "hashtags": [{"name": "glseries"}, {"name": "foumbam"}],
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "CP Edit")

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Drama Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Thailand",
            "visual_summary": (
                "Two female actresses share romantic off-screen chemistry."
            ),
            "evidence": ["two women", "real actresses", "romantic chemistry"],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_gl_relationship_with_visible_pair_and_gl_marker_routes_to_cp(self):
        original = {
            "creative_type": ["Relationship"],
            "narrative": "friends in bunny ears",
            "content_details": (
                "Two women make cute gestures and hearts at the camera."
            ),
        }
        routed = promote_entertainment_news_label(original, {
            "text": "Cute moment #glseries #foumbam",
            "hashtags": [{"name": "glseries"}, {"name": "foumbam"}],
        })
        self.assertEqual(
            routed["creative_type"],
            ["Movie/Tv/Drama Edits", "Relationship"],
        )
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["Drama Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Thailand",
            "visual_summary": "Two women make heart gestures together at the camera.",
            "evidence": ["two women", "heart gestures", "real people at camera"],
        }, {
            "text": "Cute moment #glseries #foumbam",
            "hashtags": [{"name": "glseries"}, {"name": "foumbam"}],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_ambiguous_gl_pair_without_real_world_context_is_flagged(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Relationship"],
            "narrative": "illustrated romantic pair",
            "content_details": (
                "An illustrated poster presents two women with romantic chemistry."
            ),
        }, {
            "text": "New story #glseries",
            "hashtags": [{"name": "glseries"}],
        })
        self.assertEqual(routed["creative_type"], ["Relationship"])
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("BL/GL CP edit", routed["review_risk_reasons"])

    def test_gl_fan_service_feeding_each_other_routes_to_cp(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "Idol fan service interaction",
            "content_details": (
                "At an iQIYI fan meet, two female celebrities feed each other "
                "durian on stage."
            ),
        })
        self.assertEqual(routed["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["Drama Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "China",
            "visual_summary": (
                "Two female celebrities share fan service while feeding each "
                "other at a fan meet."
            ),
            "evidence": ["two female celebrities", "feeding each other", "fan meet"],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_gl_pair_promotion_takes_priority_over_carousel_format(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "Chinese drama star promotion",
            "content_details": (
                "A portrait slideshow of actresses promoting their paired drama "
                "appearance at a public event."
            ),
        }, {
            "text": "Meet the pair at Siam Paragon #glseries",
            "hashtags": [{"name": "glseries"}],
        })
        self.assertIn("Movie/Tv/Drama Edits", routed["creative_type"])
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

    def test_girl_love_girl_hashtag_routes_real_actress_carousel_to_gl_cp(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "actresses at promotional appearance",
            "content_details": (
                "A carousel shows two Chinese actresses appearing together "
                "at a public promotional event."
            ),
        }, {
            "text": "Pair event #girllovegirl #fanlongth",
            "hashtags": [{"name": "girllovegirl"}, {"name": "fanlongth"}],
        })
        self.assertIn("Movie/Tv/Drama Edits", routed["creative_type"])
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["Actor/Actress Carousel"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "China",
            "visual_summary": "Two actresses interact together at a promotional event.",
            "evidence": ["two actresses", "promotional event", "real people"],
        }, {
            "text": "Pair event #girllovegirl #fanlongth",
            "hashtags": [{"name": "girllovegirl"}, {"name": "fanlongth"}],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_two_actresses_posing_affectionately_routes_relationship_to_gl_cp(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Lip Sync", "Relationship"],
            "narrative": "couple in bunny ears",
            "content_details": (
                "Two female Thai celebrities pose together in a cute, "
                "affectionate way while mouthing to music."
            ),
        })
        self.assertIn("Movie/Tv/Drama Edits", routed["creative_type"])
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["CP Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Thailand",
            "visual_summary": "Two female celebrities pose affectionately together.",
            "evidence": ["two women", "pose together", "real celebrities"],
        })
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_plural_actresses_eating_together_on_stage_routes_to_gl_cp(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "Chinese actresses eating durian",
            "content_details": (
                "Real-life Chinese actresses in traditional drama costumes "
                "are on stage eating durian together."
            ),
        })
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")
        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["Drama Edit"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "China",
            "visual_summary": "Chinese actresses eat durian together on stage.",
            "evidence": ["real actresses", "eating together", "on stage"],
        })
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_single_bl_actor_career_carousel_stays_actor_carousel(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "Actor career journey",
            "content_details": (
                "A photo carousel of one Thai actor and his journey from university "
                "campus star to BL series lead."
            ),
        }, {
            "text": "Career journey #thaibl",
            "hashtags": [{"name": "thaibl"}],
        })
        self.assertEqual(
            routed["_drama_content_kind_hint"],
            "Actor/Actress Carousel",
        )

    def test_two_celebrities_without_romance_do_not_route_to_cp(self):
        original = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "idol interview",
            "content_details": "Two celebrities joke during an interview.",
        }
        routed = promote_entertainment_news_label(original)
        self.assertNotEqual(routed.get("_drama_content_kind_hint"), "CP Edit")

    def test_fictional_same_gender_scene_does_not_use_real_person_cp_promotion(self):
        original = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "romantic couple scene",
            "content_details": (
                "Two male fictional characters embrace in a scripted episode scene."
            ),
        }
        self.assertEqual(promote_entertainment_news_label(original), original)

    def test_actor_photo_carousel_routes_to_actor_carousel_details(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "Chinese actor profile",
            "content_details": (
                "A photo carousel featuring portrait images of a Chinese actor "
                "with overlaid facts."
            ),
        })
        self.assertEqual(
            promoted["creative_type"],
            ["Carousel", "Movie/Tv/Drama Edits"],
        )
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Actor/Actress Carousel",
        )

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Drama Carousel"],
            "country_region": "China",
            "visual_summary": "A multi-image portrait carousel of a real actor.",
        })
        self.assertEqual(
            enriched["content_categories"],
            ["Actor/Actress Carousel"],
        )

    def test_drama_stills_carousel_overrides_actor_and_news_categories(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "narrative": "Chinese drama updates",
            "content_details": "A carousel of actors shown in drama stills.",
        }
        enriched = apply_drama_enrichment(result, {
            "content_categories": ["Entertainment News", "Actor/Actress Carousel"],
            "country_region": "China",
            "visual_summary": (
                "A promotional carousel featuring actors as their drama "
                "characters and stills from upcoming Chinese dramas."
            ),
        })
        self.assertEqual(enriched["content_categories"], ["Drama Carousel"])

    def test_behind_the_scenes_without_pair_purpose_drops_weak_cp(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama behind-the-scenes humor",
            "content_details": "Actors film an underwater scene with wire rigging.",
        }
        enriched = apply_drama_enrichment(result, {
            "content_categories": ["Behind-the-Scenes Edit", "CP Edit"],
            "country_region": "China",
            "visual_summary": (
                "A behind-the-scenes look at actors filming a pool sequence "
                "with wire rigging and a camera crew."
            ),
        })
        self.assertEqual(enriched["content_categories"], ["Behind-the-Scenes Edit"])

    def test_mascot_quiz_routes_media_to_entertainment_news(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Media/Infotainment"],
            "narrative": "Guess the mascot game",
            "content_details": (
                "Digital quiz cards ask viewers to guess the mascot name."
            ),
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Entertainment News",
        )

    def test_upcoming_drama_announcement_routes_media_carousel_to_news(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Media/Infotainment"],
            "narrative": "Upcoming drama announcements",
            "content_details": (
                "A photo carousel with actors and promotional images for "
                "upcoming Chinese series releases."
            ),
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Entertainment News",
        )

    def test_drama_release_schedule_routes_media_carousel_to_news(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Media/Infotainment"],
            "narrative": "Drama release schedule",
            "content_details": (
                "A carousel lists the July release schedule for upcoming "
                "Chinese drama series."
            ),
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "Entertainment News")

    def test_real_actress_look_comparison_routes_to_actor_carousel(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "narrative": "cdrama heroine look comparison",
            "content_details": (
                "A six-slide carousel comparing Chinese actresses in minimalist "
                "versus elaborate costume looks."
            ),
        })
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Actor/Actress Carousel",
        )

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Drama Carousel"],
            "country_region": "China",
            "visual_summary": (
                "A photo carousel comparing the costume looks of real Chinese "
                "actresses."
            ),
        })
        self.assertEqual(enriched["content_categories"], ["Actor/Actress Carousel"])

    def test_actor_behind_scenes_montage_routes_to_bts_detail(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "celebrity behind the scenes",
            "content_details": (
                "A montage of actor Liu Yuning interacting with cast members "
                "behind the scenes of a production."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Behind-the-Scenes Edit",
        )

    def test_celebrity_profile_split_screen_routes_to_actor_carousel(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "celebrity child spotlight",
            "content_details": (
                "A split-screen image shows celebrity Chompoo Araya and her "
                "daughter in two public-appearance portraits."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Actor/Actress Carousel",
        )

    def test_explicit_gl_pair_lipsync_together_routes_to_cp(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Lip Sync", "Lyrics"],
            "narrative": "friends in bunny ears",
            "content_details": (
                "Two female friends wear matching headbands and lip-sync "
                "together at the camera."
            ),
        }, {
            "text": "#thaigl #glseries #oombam",
            "hashtags": [{"name": "thaigl"}, {"name": "glseries"}],
        })
        self.assertIn("Movie/Tv/Drama Edits", promoted["creative_type"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "CP Edit")

    def test_actor_hashtag_without_carousel_structure_does_not_route(self):
        original = {
            "creative_type": ["Celebrity Edits"],
            "narrative": "Chinese actor interview",
            "content_details": "A single video clip of an actor speaking.",
        }
        routed = promote_entertainment_news_label(original, {
            "text": "Interview #chenglei",
            "hashtags": [{"name": "chenglei"}],
        })
        self.assertNotEqual(
            routed.get("_drama_content_kind_hint"),
            "Actor/Actress Carousel",
        )

    def test_fictional_scene_carousel_is_not_actor_carousel(self):
        original = {
            "creative_type": ["Carousel", "Celebrity Edits"],
            "narrative": "drama character slideshow",
            "content_details": (
                "A photo carousel of fictional characters and scripted drama scenes."
            ),
        }
        self.assertEqual(promote_entertainment_news_label(original), original)

    def test_bl_actor_net_worth_ranking_is_actor_carousel_not_cp_or_drama(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "narrative": "Thai BL actor ranking",
            "content_details": (
                "A slideshow of several real Thai actors with text comparing "
                "their 2026 net worth."
            ),
        }, {
            "text": "Thai stars ranked #blseries #anonattawin #joongarchen",
            "hashtags": [
                {"name": "blseries"},
                {"name": "anonattawin"},
                {"name": "joongarchen"},
            ],
        })
        self.assertEqual(
            routed["_drama_content_kind_hint"],
            "Actor/Actress Carousel",
        )

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["CP Edit", "Drama Carousel"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "country_region": "Thailand",
            "visual_summary": "A ranking carousel of several real Thai actors.",
        })
        self.assertEqual(
            enriched["content_categories"],
            ["Actor/Actress Carousel"],
        )

    def test_gl_pair_in_retail_setting_with_hearts_routes_to_cp(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Relationship"],
            "narrative": "friends in bunny ears",
            "content_details": (
                "Two female celebrities in a retail setting wear matching "
                "animal-ear headbands and make heart gestures together."
            ),
        }, {
            "text": "Cute pair #thaigl #glseries #oombam",
            "hashtags": [
                {"name": "thaigl"},
                {"name": "glseries"},
                {"name": "oombam"},
            ],
        })
        self.assertEqual(routed["_drama_content_kind_hint"], "CP Edit")

    def test_entertainment_news_drops_unsupported_cp_and_drama_carousel(self):
        routed = promote_entertainment_news_label({
            "creative_type": ["Carousel", "Media/Infotainment"],
            "narrative": "Drama trope explainer",
            "content_details": (
                "An informational carousel discusses common romantic drama "
                "tropes and recommends several series."
            ),
        })
        self.assertEqual(routed["_drama_content_kind_hint"], "Entertainment News")

        enriched = apply_drama_enrichment(routed, {
            "content_categories": ["Entertainment News", "Drama Carousel", "CP Edit"],
            "country_region": "China",
            "visual_summary": "An informational drama-trope explainer.",
        })
        self.assertEqual(enriched["content_categories"], ["Entertainment News"])

    def test_actress_daily_activity_montage_routes_to_daily_vlog(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "idol lifestyle",
            "content_details": (
                "A montage featuring Malaysian celebrity Sophia Albarakbah "
                "interacting with a kitten and doing creative activities at "
                "an art studio."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Actor/Actress Daily Vlog",
        )

        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["Drama Edit"],
            "country_region": "Malaysia",
            "visual_summary": "An actress spends time with a kitten in an art studio.",
        })
        self.assertEqual(
            enriched["content_categories"],
            ["Actor/Actress Daily Vlog"],
        )
        self.assertIn(
            "Content Category: Actor/Actress Daily Vlog",
            enriched["content_details"],
        )

    def test_actress_travel_lifestyle_montage_removes_unsupported_dance(self):
        promoted = promote_entertainment_news_label({
            "creative_type": ["Dance", "Celebrity Edits"],
            "narrative": "daily life aesthetic",
            "content_details": (
                "A montage showcasing Malaysian actress Sophia Albarakbah in "
                "various locations including Japan, featuring casual and "
                "travel-themed promotional shots."
            ),
        })
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertNotIn("Dance", promoted["creative_type"])
        self.assertEqual(
            promoted["_drama_content_kind_hint"],
            "Actor/Actress Daily Vlog",
        )

    def test_review_builder_accepts_two_observed_categories(self):
        updates = build_review_drama_updates({
            "visual_summary": "Real actors interact behind the scenes.",
            "content_categories": ["CP Edit", "Behind-the-Scenes Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "drama_format": "Short-form Drama",
            "country_region": "Thailand",
            "drama_title": "Example Series",
            "detected_audio": "Hit The Wall",
            "campaign_song_match": "Matched",
            "audio_version": "Original",
        })
        self.assertEqual(updates["Drama Content Category"], "CP Edit, Behind-the-Scenes Edit")
        self.assertIn("Content Category: CP Edit, Behind-the-Scenes Edit", updates["Content Details"])
        self.assertNotIn("Format:", updates["Content Details"])
        self.assertEqual(updates["Drama Format"], "")

    def test_explicit_thai_gl_pair_promotes_celebrity_edit_to_drama_family(self):
        row = {
            "text": (
                "ตั้งใจจะโสด แต่ไม่โสดนะซับบบ #อุ้มแบม #อุ้มอิษยา "
                "#แบมสราลี #thaigl #glseries #oombam"
            )
        }
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "friends hanging out",
            "content_details": (
                "Two Thai actresses/celebrities, Oom and Bam, are shown "
                "together in close-up playful shots, wearing animal ear "
                "headbands and making cute poses to the camera."
            ),
        }, row)
        self.assertEqual(promoted["creative_type"], ["Movie/Tv/Drama Edits"])
        self.assertEqual(promoted["_drama_content_kind_hint"], "CP Edit")
        self.assertFalse(promoted.get("needs_human_review", False))

    def test_explicit_thai_gl_pair_resolves_gl_cp_details(self):
        row = {
            "text": (
                "ตั้งใจจะโสด แต่ไม่โสดนะซับบบ #อุ้มแบม #thaigl "
                "#glseries #oombam"
            )
        }
        promoted = promote_entertainment_news_label({
            "creative_type": ["Celebrity Edits"],
            "narrative": "friends hanging out",
            "content_details": (
                "Two Thai actresses Oom and Bam pose together in close-up "
                "playful shots and make cute poses to the camera."
            ),
        }, row)
        enriched = apply_drama_enrichment(promoted, {
            "content_categories": ["CP Edit"],
            "visual_summary": (
                "Two Thai actresses Oom and Bam pose together in playful "
                "close-up shots and make cute poses to the camera."
            ),
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "country_region": "Thailand",
            "detected_audio": "ตั้งใจจะโสด",
            "audio_version": "Original",
            "evidence": ["#thaigl #glseries #oombam; two actresses together"],
        }, row=row)
        self.assertEqual(enriched["content_categories"], ["CP Edit"])
        self.assertEqual(enriched["drama_type"], "GL Drama")
        self.assertEqual(enriched["edit_focus"], "GL CP Edit")

    def test_entertainment_news_review_hides_mixed_drama_fields(self):
        updates = build_review_drama_updates({
            "visual_summary": "A creator reports K-pop celebrity breakup news.",
            "content_categories": ["Entertainment News", "CP Edit"],
            "drama_type": "BL Drama",
            "edit_focus": "BL CP Edit",
            "drama_format": "Long-form Drama",
            "country_region": "Korea",
            "drama_title": "Stale title",
            "detected_audio": "The One That Got Away",
            "audio_version": "Original",
        })
        self.assertEqual(updates["Drama Content Category"], "Entertainment News, CP Edit")
        self.assertEqual(updates["Drama Type"], "")
        self.assertEqual(updates["Drama Edit Focus"], "")
        self.assertEqual(updates["Drama Format"], "")
        self.assertEqual(updates["Drama Title"], "")
        self.assertIn("Country/Region: Korea", updates["Content Details"])
        self.assertIn("Detected Audio: The One That Got Away", updates["Content Details"])
        self.assertIn("Audio Version: Original", updates["Content Details"])
        self.assertNotIn("Drama Type:", updates["Content Details"])
        self.assertNotIn("Edit Focus:", updates["Content Details"])
        self.assertNotIn("Format:", updates["Content Details"])
        self.assertNotIn("Drama Title:", updates["Content Details"])

    def test_cp_only_review_derives_hidden_type_from_edit_focus(self):
        updates = build_review_drama_updates({
            "visual_summary": "Two Thai actresses appear together as a promoted pair.",
            "content_categories": ["CP Edit"],
            "drama_type": "General Drama",
            "edit_focus": "GL CP Edit",
            "drama_format": "Long-form Drama",
            "country_region": "Thailand",
            "drama_title": "Example Series",
            "detected_audio": "ตั้งใจจะโสด",
            "audio_version": "Original",
        })
        self.assertEqual(updates["Drama Type"], "GL Drama")
        self.assertEqual(updates["Drama Edit Focus"], "GL CP Edit")
        self.assertEqual(updates["Drama Format"], "")
        self.assertIn("Drama Type: GL Drama", updates["Content Details"])
        self.assertIn("Edit Focus: GL CP Edit", updates["Content Details"])
        self.assertNotIn("Format:", updates["Content Details"])

    def test_review_defaults_use_campaign_song_when_audio_is_missing(self):
        defaults = drama_review_defaults({
            "Track": "Katy Perry - The One That Got Away",
            "Detected Audio": "",
        })
        self.assertEqual(defaults["detected_audio"], "The One That Got Away")

    def test_review_defaults_replace_generic_creator_audio_with_campaign_song(self):
        defaults = drama_review_defaults({
            "Track": "The One That Got Away",
            "Detected Audio": "original sound - creator",
        })
        self.assertEqual(defaults["detected_audio"], "The One That Got Away")

    def test_review_defaults_preserve_specific_detected_audio(self):
        defaults = drama_review_defaults({
            "Track": "The One That Got Away",
            "Detected Audio": "Different Song",
        })
        self.assertEqual(defaults["detected_audio"], "Different Song")

    def test_review_defaults_ignore_placeholder_campaign_track(self):
        defaults = drama_review_defaults({
            "Track": "Not specified",
            "Detected Audio": "Unknown",
        })
        self.assertEqual(defaults["detected_audio"], "Unknown")

    def test_review_defaults_prefer_validated_export_over_stale_raw_proposal(self):
        defaults = drama_review_defaults({
            "content_categories": "Entertainment News",
            "Drama Content Category": "Drama Edit",
            "drama_type": "Unknown",
            "Drama Type": "General Drama",
            "edit_focus": "Unknown",
            "Drama Edit Focus": "Fictional Story",
            "drama_format": "Unknown",
            "Drama Format": "Short-form Drama",
            "country_region": "Unknown",
            "Drama Country/Region": "China",
            "drama_title": "Unknown",
            "Drama Title": "Depth of Love",
            "audio_version": "Unknown",
            "Audio Version": "Original",
        })
        self.assertEqual(defaults["content_categories"], ["Drama Edit"])
        self.assertEqual(defaults["drama_type"], "General Drama")
        self.assertEqual(defaults["edit_focus"], "Fictional Story")
        self.assertEqual(defaults["drama_format"], "Short-form Drama")
        self.assertEqual(defaults["country_region"], "China")
        self.assertEqual(defaults["drama_title"], "Depth of Love")
        self.assertEqual(defaults["audio_version"], "Original")

    def test_unknown_actual_drama_format_defaults_to_long_form(self):
        enriched = apply_drama_enrichment(
            {
                "creative_type": ["Movie/Tv/Drama Edits"],
                "content_details": "A montage from a Chinese television drama.",
            },
            {
                "content_categories": ["Drama Edit"],
                "drama_type": "General Drama",
                "edit_focus": "Fictional Story",
                "drama_format": "Unknown",
                "country_region": "China",
                "drama_title": "Story of Kunning Palace",
                "visual_summary": "A romantic montage from Story of Kunning Palace.",
            },
            {},
        )
        self.assertEqual(enriched["drama_format"], "Long-form Drama")
        self.assertIn("Format: Long-form Drama", enriched["content_details"])

    def test_non_drama_detail_category_omits_format_instead_of_unknown(self):
        enriched = apply_drama_enrichment(
            {
                "creative_type": ["Movie/Tv/Drama Edits"],
                "content_details": "K-pop idols exchange jokes during an interview.",
                "_drama_content_kind_hint": "K-pop Show Cut",
            },
            {
                "content_categories": ["Entertainment News"],
                "drama_format": "Unknown",
                "country_region": "Korea",
                "visual_summary": "A clipped K-pop variety-show interview.",
            },
            {},
        )
        self.assertEqual(enriched["drama_format"], "Not applicable")
        self.assertNotIn("Format:", enriched["content_details"])
        self.assertEqual(drama_export_values(enriched)["Drama Format"], "")

    def test_legacy_drama_export_normalizes_unknown_format(self):
        legacy = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "drama_format": "Unknown",
            "country_region": "China",
            "drama_title": "Story of Kunning Palace",
            "content_details": "A montage from a television drama.",
        }
        self.assertEqual(
            drama_export_values(legacy)["Drama Format"],
            "Long-form Drama",
        )

    def test_campaign_market_does_not_become_drama_region(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A fictional scene.",
        }
        response = {
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Unknown",
            "country_region": "Unknown",
            "drama_title": "Unknown",
            "evidence": ["fictional scene"],
        }
        enriched = apply_drama_enrichment(result, response, {"_campaign_market": "TH"})
        self.assertEqual(enriched["country_region"], "Unknown")

    def test_bl_series_fictional_scenes_override_entertainment_news(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": (
                "A collection of emotional scenes from a Chinese short drama."
            ),
        }
        response = {
            "content_categories": ["Entertainment News"],
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "drama_format": "Short-form Drama",
            "country_region": "China",
            "drama_title": "Double Helix",
            "visual_summary": (
                "A montage of emotional scenes from the Chinese short drama "
                "Double Helix."
            ),
            "evidence": ["The post shows scripted scenes from the series."],
        }
        row = {
            "text": (
                "In the end, he still decided to leave "
                "#cdrama #DOUBLEHELIX #blseries #shortfilm #SHUANGCHENG"
            ),
            "hashtags": [
                {"name": "cdrama"},
                {"name": "DOUBLEHELIX"},
                {"name": "blseries"},
                {"name": "shortfilm"},
            ],
        }
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["content_categories"], ["Drama Edit"])
        self.assertEqual(enriched["drama_type"], "BL Drama")
        self.assertEqual(enriched["edit_focus"], "Fictional Story")

    def test_bl_hashtag_does_not_turn_real_interview_into_drama_edit(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits", "Celebrity Edits"],
            "narrative": "Actor interview",
            "content_details": "Two BL actors answer questions at a press event.",
        }
        response = {
            "content_categories": ["Entertainment News"],
            "country_region": "Thailand",
            "visual_summary": (
                "Two actors sit with a host and answer interview questions."
            ),
            "evidence": ["A branded microphone and interviewer are visible."],
        }
        row = {
            "text": "Cast interview #blseries #drama",
            "hashtags": [{"name": "blseries"}, {"name": "drama"}],
        }
        enriched = apply_drama_enrichment(result, response, row)
        self.assertEqual(enriched["content_categories"], ["Entertainment News"])

    def test_thai_campaign_context_does_not_override_chinese_production_region(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Behind-the-scenes footage from The First Jasmine.",
        }
        response = {
            "content_categories": ["Behind-the-Scenes Edit"],
            "country_region": "China",
            "drama_title": "The First Jasmine",
            "visual_summary": "Behind-the-scenes footage from the set of The First Jasmine.",
            "evidence": [
                "The caption is in Thai.",
                "The hashtags use Thai language.",
                "The campaign song is Thai.",
            ],
        }
        enriched = apply_drama_enrichment(
            result,
            response,
            {
                "_campaign_market": "TH",
                "_campaign_track": "Thai campaign song",
                "text": "Thai caption and hashtags",
            },
        )
        self.assertEqual(enriched["country_region"], "China")
        self.assertNotIn(
            "Region suggestion",
            str(enriched.get("review_risk_reasons", "")),
        )

    def test_explicit_chinese_production_evidence_corrects_wrong_region(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Production footage from a television drama.",
        }
        response = {
            "content_categories": ["Behind-the-Scenes Edit"],
            "country_region": "Thailand",
            "drama_title": "The First Jasmine",
            "visual_summary": "Behind-the-scenes footage from a Chinese drama production.",
            "evidence": ["The campaign uses a Thai song."],
        }
        enriched = apply_drama_enrichment(result, response, {"_campaign_market": "TH"})
        self.assertEqual(enriched["country_region"], "China")
        self.assertTrue(enriched["needs_human_review"])
        self.assertIn(
            "explicit China visual evidence",
            enriched["review_risk_reasons"],
        )

    def test_china_entertainment_source_corrects_campaign_market_leakage(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "celebrity fan service",
            "content_details": "Two actresses interact at an entertainment event.",
        }
        response = {
            "content_categories": ["CP Edit"],
            "drama_type": "GL Drama",
            "edit_focus": "GL CP Edit",
            "country_region": "Thailand",
            "visual_summary": "Two actresses feed each other on stage.",
            "evidence": ["A real-person promotional event is visible."],
        }
        enriched = apply_drama_enrichment(
            result,
            response,
            {
                "_campaign_market": "TH",
                "Creator": "chinaentertain_daily",
                "text": "Thai-language campaign caption",
            },
        )
        self.assertEqual(enriched["country_region"], "China")
        self.assertTrue(enriched["needs_human_review"])
        self.assertIn("explicit China visual evidence", enriched["review_risk_reasons"])

    def test_weak_thai_context_in_mixed_sentence_does_not_create_region_conflict(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "Behind-the-scenes footage from The First Jasmine.",
        }
        response = {
            "content_categories": ["Behind-the-Scenes Edit"],
            "country_region": "China",
            "drama_title": "The First Jasmine",
            "visual_summary": (
                "Thai song captions accompany behind-the-scenes footage "
                "from The First Jasmine."
            ),
            "evidence": [],
        }
        enriched = apply_drama_enrichment(result, response, {"_campaign_market": "TH"})
        self.assertEqual(enriched["country_region"], "China")
        self.assertNotIn(
            "Region suggestion",
            str(enriched.get("review_risk_reasons", "")),
        )

    def test_metadata_speed_and_itunes_identity_are_conservative(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A drama montage.",
        }
        response = {
            "drama_type": "General Drama",
            "edit_focus": "General Drama Edit",
            "drama_format": "Fan Edit",
            "country_region": "Korea",
            "drama_title": "Unknown",
            "evidence": ["edited drama montage"],
        }
        row = {
            "_campaign_track": "Example Artist - Example Song",
            "musicMeta": {
                "musicName": "Example Song sped up",
                "musicAuthor": "Example Artist",
            },
        }
        enriched = apply_drama_enrichment(result, response, row, http_get=_itunes_get)
        self.assertEqual(enriched["campaign_song_match"], "Matched")
        self.assertEqual(enriched["audio_version"], "Sped Up")

    def test_exact_official_metadata_match_resolves_original(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A Chinese drama montage.",
        }
        response = {
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Short-form Drama",
            "country_region": "China",
            "drama_title": "Victory in Love and War",
            "visual_summary": "A Chinese short-form drama montage.",
            "evidence": ["Chinese short-drama format"],
            "audio_version": "Audio Review",
        }
        row = {
            "_campaign_track": "Example Song",
            "musicMeta": {"musicName": "Example Song", "musicAuthor": "Example Artist"},
        }
        enriched = apply_drama_enrichment(result, response, row, http_get=_itunes_get)
        self.assertEqual(enriched["campaign_song_match"], "Matched")
        self.assertEqual(enriched["audio_version"], "Original")
        self.assertNotIn("Audio Review", enriched["content_details"])

    def test_exact_tiktok_sound_title_resolves_original_without_apple(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A drama montage.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Unknown",
            "country_region": "China",
            "drama_title": "Unknown",
        }
        row = {
            "_campaign_track": "Hit The Wall",
            "musicMeta": {"musicName": "Hit The Wall", "musicAuthor": "Gracie Abrams"},
        }

        def empty_itunes(*_args, **_kwargs):
            return _Response({"results": []})

        enriched = apply_drama_enrichment(result, response, row, http_get=empty_itunes)
        self.assertEqual(enriched["audio_version"], "Original")
        self.assertNotIn("Campaign Song Match:", enriched["content_details"])

    def test_waveform_comparison_can_replace_metadata_original_with_slowed(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "content_kind": "Drama Edit",
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Short-form Drama",
            "country_region": "China",
            "drama_title": "Example Drama",
            "detected_audio": "Hit The Wall",
            "audio_version": "Original",
            "visual_summary": "A fictional short-drama montage.",
            "content_details": "Old details",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Slowed",
            "audio_evidence": "Direct preview comparison",
            "similarity": 0.91,
        })
        self.assertEqual(updated["audio_version"], "Slowed")
        self.assertIn("Audio Version: Slowed", updated["content_details"])

    def test_audio_comparison_normalizes_legacy_micro_drama_format(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "content_kind": "Drama Edit",
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Micro-drama",
            "country_region": "China",
            "drama_title": "Example Drama",
            "detected_audio": "Example Song",
            "audio_version": "Unknown",
            "visual_summary": "A fictional short-form drama montage.",
            "content_details": "Old details",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Original",
            "audio_evidence": "Direct preview comparison",
            "similarity": 0.91,
        })
        self.assertIn("Format: Short-form Drama", updated["content_details"])

    def test_explicit_speed_metadata_is_not_overwritten_by_waveform_original(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "content_kind": "Drama Edit",
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Unknown",
            "country_region": "Unknown",
            "drama_title": "Unknown",
            "detected_audio": "Example Song sped up",
            "audio_version": "Sped Up",
            "visual_summary": "A drama montage.",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Original",
            "audio_evidence": "Weak preview comparison",
            "similarity": 0.83,
        })
        self.assertEqual(updated["audio_version"], "Sped Up")

    def test_explicit_remix_metadata_is_supported_but_not_inferred_from_waveform(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A drama montage.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "country_region": "Korea",
            "drama_title": "Example Drama",
        }
        row = {
            "_campaign_track": "Example Artist - Example Song",
            "musicMeta": {
                "musicName": "Example Song remix",
                "musicAuthor": "Example Artist",
            },
        }
        enriched = apply_drama_enrichment(result, response, row, http_get=_itunes_get)
        self.assertEqual(enriched["audio_version"], "Remix")
        updated = apply_audio_comparison(enriched, {
            "audio_version": "Original",
            "audio_evidence": "Preview comparison cannot disprove explicit remix metadata.",
            "similarity": 0.90,
        })
        self.assertEqual(updated["audio_version"], "Remix")

    def test_confident_waveform_match_replaces_generic_vietnamese_audio_title(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "content_kind": "Drama Edit",
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Unknown",
            "country_region": "Vietnam",
            "drama_title": "Unknown",
            "detected_audio": "nhạc nền - 🐽",
            "audio_version": "Unknown",
            "itunes_track": "Example Artist - Example Song",
            "visual_summary": "A drama montage.",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Original",
            "audio_evidence": "Direct preview comparison",
            "similarity": 0.90,
        })
        self.assertEqual(updated["detected_audio"], "Example Song")
        self.assertEqual(updated["audio_version"], "Original")

    def test_generic_chinese_creator_audio_displays_supplied_campaign_track(self):
        resolved = resolve_audio_fields(
            {
                "detected_audio": "原声 - uhfian",
                "_verified_itunes": {},
            },
            {
                "musicMeta.musicName": "原声 - uhfian",
                "musicMeta.musicAuthor": "uhfian",
                "_campaign_track": "The One That Got Away",
            },
        )
        self.assertEqual(resolved["detected_audio"], "The One That Got Away")
        self.assertEqual(resolved["campaign_song_match"], "Unknown")

    def test_campaign_track_wins_over_model_guess_when_metadata_is_generic(self):
        resolved = resolve_audio_fields(
            {
                "detected_audio": "Different Song",
                "_verified_itunes": {},
            },
            {
                "musicMeta.musicName": "原声 - uhfian",
                "musicMeta.musicAuthor": "uhfian",
                "_campaign_track": "Katy Perry - The One That Got Away",
            },
        )
        self.assertEqual(resolved["detected_audio"], "The One That Got Away")
        self.assertEqual(resolved["campaign_song_match"], "Unknown")

    def test_placeholder_campaign_track_does_not_replace_generic_audio(self):
        resolved = resolve_audio_fields(
            {
                "detected_audio": "Different Song",
                "_verified_itunes": {},
            },
            {
                "musicMeta.musicName": "原声 - uhfian",
                "musicMeta.musicAuthor": "uhfian",
                "_campaign_track": "Not specified",
            },
        )
        self.assertEqual(resolved["detected_audio"], "Different Song")

    def test_explicit_audio_title_still_wins_over_campaign_track(self):
        resolved = resolve_audio_fields(
            {
                "detected_audio": "The One That Got Away",
                "_verified_itunes": {},
            },
            {
                "musicMeta.musicName": "Another Song",
                "musicMeta.musicAuthor": "Example Artist",
                "_campaign_track": "The One That Got Away",
            },
        )
        self.assertEqual(resolved["detected_audio"], "Another Song")

    def test_generic_creator_audio_without_campaign_track_is_preserved(self):
        resolved = resolve_audio_fields(
            {"detected_audio": "原声 - uhfian"},
            {
                "musicMeta.musicName": "原声 - uhfian",
                "musicMeta.musicAuthor": "uhfian",
            },
        )
        self.assertEqual(resolved["detected_audio"], "原声 - uhfian")

    def test_generic_original_sound_defaults_to_original_for_kpop_show_cut(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["K-pop Show Cut"],
            "content_kind": "K-pop Show Cut",
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "drama_format": "Not applicable",
            "country_region": "Korea",
            "drama_title": "Unknown",
            "detected_audio": "original sound - idol.buzz",
            "audio_version": "Unknown",
            "visual_summary": "A clipped K-pop variety-show segment.",
            "content_details": "Old details",
        }
        updated = apply_generic_original_audio_default(
            result,
            {
                "musicMeta.musicName": "original sound - idol.buzz",
                "musicMeta.musicAuthor": "idol.buzz",
                "_campaign_track": "Not specified",
            },
        )
        self.assertEqual(updated["audio_version"], "Original")
        self.assertEqual(
            updated["audio_version_basis"],
            "generic-tiktok-original-sound-default",
        )
        self.assertIn("Audio Version: Original", updated["content_details"])

    def test_generic_original_sound_defaults_to_original_for_daily_vlog(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Actor/Actress Daily Vlog"],
            "content_kind": "Actor/Actress Daily Vlog",
            "drama_format": "Not applicable",
            "detected_audio": "original sound - edit.mera",
            "audio_version": "Unknown",
        }
        updated = apply_generic_original_audio_default(result, {})
        self.assertEqual(updated["audio_version"], "Original")

    def test_generic_original_default_does_not_override_ambiguous_comparison(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "detected_audio": "original sound - creator",
            "audio_version": "Unknown",
            "audio_comparison_review_recommended": True,
        }
        self.assertEqual(
            apply_generic_original_audio_default(result, {})["audio_version"],
            "Unknown",
        )

    def test_generic_original_default_preserves_explicit_slowed_version(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "detected_audio": "original sound - creator",
            "audio_version": "Slowed",
        }
        self.assertEqual(
            apply_generic_original_audio_default(result, {})["audio_version"],
            "Slowed",
        )

    def test_weak_waveform_result_stays_unknown_without_review(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Anime Edit"],
            "content_kind": "Anime Edit",
            "drama_type": "Unknown",
            "edit_focus": "Unknown",
            "drama_format": "Unknown",
            "country_region": "Japan",
            "drama_title": "Example Anime",
            "detected_audio": "original sound",
            "audio_version": "Unknown",
            "visual_summary": "An anime character montage.",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Unknown",
            "audio_evidence": "Preview segments did not align",
            "similarity": 0.31,
            "comparison_status": "unusable",
            "review_recommended": False,
        })
        self.assertEqual(updated["audio_version"], "Unknown")
        self.assertFalse(updated["audio_comparison_review_recommended"])
        self.assertNotIn("drama_review_reason", updated)

    def test_moderate_original_leading_match_is_labelled_original(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "audio_version": "Unknown",
            "content_details": "A drama montage.",
        }
        updated = apply_audio_comparison(result, {
            "audio_version": "Original",
            "audio_evidence": "Original was the strongest moderate match",
            "similarity": 0.73,
            "original_score": 0.73,
            "alternative_score": 0.69,
            "comparison_status": "confident",
            "review_recommended": False,
        })
        self.assertEqual(updated["audio_version"], "Original")
        self.assertIn("Audio Version: Original", updated["content_details"])

    def test_unknown_requested_drama_audio_is_routed_to_human_review(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "audio_version": "Unknown",
            "audio_comparison_review_recommended": True,
            "needs_human_review": False,
        }
        routed = route_unknown_drama_audio_to_review(
            result,
            {"_campaign_track": "The One That Got Away"},
        )
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("close or contradictory", routed["review_risk_reasons"])

    def test_unknown_weak_audio_does_not_force_review(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "audio_version": "Unknown",
            "audio_comparison_review_recommended": False,
            "needs_human_review": False,
        }
        routed = route_unknown_drama_audio_to_review(
            result,
            {"_campaign_track": "The One That Got Away"},
        )
        self.assertFalse(routed["needs_human_review"])

    def test_unknown_audio_without_campaign_track_does_not_force_review(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "audio_version": "Unknown",
            "needs_human_review": False,
        }
        self.assertEqual(route_unknown_drama_audio_to_review(result, {}), result)

    def test_thai_actor_ranking_mislabeled_as_news_is_routed_to_review(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Entertainment News"],
            "narrative": "Thai BL actor ranking",
            "content_details": (
                "A photo carousel ranking Thai BL actors by estimated net worth."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"Market": "TH", "isSlideshow": True},
        )
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("actor/profile evidence conflicts", routed["review_risk_reasons"])

    def test_non_thai_profile_carousel_conflict_is_also_routed_to_review(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Carousel"],
            "narrative": "cdrama heroine look comparison",
            "content_details": (
                "A carousel comparing real actresses and their costume looks."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"Market": "Other", "isSlideshow": True},
        )
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("actor/profile evidence conflicts", routed["review_risk_reasons"])

    def test_thai_trope_discussion_mislabeled_as_drama_carousel_is_reviewed(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Carousel"],
            "narrative": "Chinese drama trope discussion",
            "content_details": (
                "A carousel of female leads from historical dramas discussing "
                "the trope of poor heroines."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"_campaign_market": "TH", "isSlideshow": True},
        )
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("informational evidence conflicts", routed["review_risk_reasons"])

    def test_thai_entertainment_carousel_without_detail_category_is_reviewed(self):
        result = {
            "creative_type": ["Carousel", "Media/Infotainment"],
            "narrative": "cooking tutorial",
            "content_details": (
                "A four-image slideshow showing a drink tutorial inspired by a "
                "Chinese actor."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"market": "Thailand", "isSlideshow": True},
        )
        self.assertTrue(routed["needs_human_review"])
        self.assertIn("detailed subtype is missing", routed["review_risk_reasons"])

    def test_strong_thai_actor_profile_carousel_remains_automatic(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Actor/Actress Carousel"],
            "narrative": "Thai actor career ranking",
            "content_details": (
                "A multi-image actor profile ranking public appearances and "
                "career facts."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"Market": "TH", "isSlideshow": True},
        )
        self.assertFalse(routed["needs_human_review"])

    def test_strong_thai_fictional_drama_carousel_remains_automatic(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Carousel"],
            "narrative": "Drama character introduction",
            "content_details": (
                "A six-image carousel introducing fictional drama characters "
                "with promotional stills and relationship cards."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"Market": "TH", "isSlideshow": True},
        )
        self.assertFalse(routed["needs_human_review"])

    def test_strong_thai_gl_cp_carousel_remains_automatic(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["CP Edit"],
            "narrative": "friends day out",
            "content_details": (
                "Two actresses film themselves in a playful interaction while "
                "wearing matching accessories."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {
                "Market": "TH",
                "isSlideshow": True,
                "text": "#thaigl #glseries #oombam",
            },
        )
        self.assertFalse(routed["needs_human_review"])

    def test_explicit_thai_bts_carousel_remains_automatic(self):
        result = {
            "creative_type": ["Carousel", "Movie/Tv/Drama Edits"],
            "content_categories": ["Behind-the-Scenes Edit"],
            "narrative": "Drama behind the scenes",
            "content_details": (
                "Behind-the-scenes footage and funny outtakes filmed on set."
            ),
            "needs_human_review": False,
        }
        routed = route_thailand_carousel_ambiguity_to_review(
            result,
            {"Market": "TH", "isSlideshow": True},
        )
        self.assertFalse(routed["needs_human_review"])

    def test_chinese_short_drama_uses_short_form_drama(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_details": "A drama montage.",
        }
        response = {
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Short-form Drama",
            "country_region": "China",
            "drama_title": "Victory in Love and War",
            "visual_summary": "A montage from a Chinese short-form drama.",
            "evidence": ["The title is associated with the Chinese short-drama format."],
        }
        enriched = apply_drama_enrichment(result, response, {})
        self.assertEqual(enriched["drama_format"], "Short-form Drama")
        self.assertIn("Format: Short-form Drama", enriched["content_details"])

    def test_reviewed_still_love_title_overrides_long_form_model_guess(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": "An emotional fictional story scene.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Long-form Drama",
            "country_region": "China",
            "drama_title": "Still Love",
            "visual_summary": "A montage of fictional scenes between the leads.",
        }
        enriched = apply_drama_enrichment(result, response, {"Track": "Pelarian"})
        self.assertEqual(enriched["drama_format"], "Short-form Drama")
        self.assertIn("Format: Short-form Drama", enriched["content_details"])

    def test_other_named_drama_keeps_explicit_long_form(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "narrative": "Drama edit",
            "content_details": "An emotional fictional story scene.",
        }
        response = {
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Long-form Drama",
            "country_region": "China",
            "drama_title": "Example Long Drama",
            "visual_summary": "A montage of fictional scenes between the leads.",
        }
        enriched = apply_drama_enrichment(result, response, {"Track": "Pelarian"})
        self.assertEqual(enriched["drama_format"], "Long-form Drama")

    def test_legacy_micro_drama_value_is_normalized_to_short_form_in_review(self):
        updates = build_review_drama_updates({
            "content_categories": ["Drama Edit"],
            "visual_summary": "A Thai short-form vertical drama episode.",
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Micro-drama",
            "country_region": "Thailand",
            "drama_title": "Example Series",
            "detected_audio": "Example Song",
            "audio_version": "Original",
        })
        self.assertEqual(updates["Drama Format"], "Short-form Drama")
        self.assertIn("Format: Short-form Drama", updates["Content Details"])

    def test_song_title_alone_is_enough_and_artist_is_optional(self):
        self.assertEqual(split_campaign_track("Example Song"), ("", "Example Song"))

        def get_with_multiple_results(*_args, **_kwargs):
            return _Response({"results": [
                {"trackName": "An Example Story", "artistName": "Wrong Artist"},
                {
                    "trackName": "Example Song",
                    "artistName": "Example Artist",
                    "previewUrl": "https://example.test/preview.m4a",
                },
            ]})

        match = fetch_itunes_preview("Example Song", http_get=get_with_multiple_results)
        self.assertEqual(match["track_name"], "Example Song")
        self.assertEqual(match["artist_name"], "Example Artist")

    def test_campaign_track_catalog_status_confirms_a_close_match(self):
        status = campaign_track_catalog_status("Example Song", http_get=_itunes_get)
        self.assertEqual(status["status"], "matched")
        self.assertEqual(status["track_name"], "Example Song")
        self.assertEqual(status["artist_name"], "Example Artist")

    def test_artist_and_song_input_disambiguates_duplicate_song_titles(self):
        def duplicate_titles(*_args, **_kwargs):
            return _Response({"results": [
                {"trackName": "Hit the Wall", "artistName": "Wrong Artist"},
                {
                    "trackName": "Hit the Wall",
                    "artistName": "Gracie Abrams",
                    "previewUrl": "https://example.test/hit-the-wall.m4a",
                },
            ]})

        match = fetch_itunes_preview(
            "Gracie Abrams - Hit the Wall",
            http_get=duplicate_titles,
        )
        self.assertEqual(match["track_name"], "Hit the Wall")
        self.assertEqual(match["artist_name"], "Gracie Abrams")

    def test_native_script_titles_match_in_their_primary_storefronts(self):
        cases = (
            ("漫步香港1999", "TW"),
            ("ตั้งใจจะโสด", "TH"),
            ("아크라포빅", "KR"),
        )
        for title, expected_storefront in cases:
            calls = []

            def localized_get(*_args, **kwargs):
                storefront = kwargs.get("params", {}).get("country")
                calls.append(storefront)
                return _Response({"results": [{
                    "trackName": title,
                    "artistName": "Local Artist",
                    "previewUrl": "https://example.test/native-preview.m4a",
                }]})

            with self.subTest(title=title):
                match = fetch_itunes_preview(title, http_get=localized_get)
                self.assertEqual(match["track_name"], title)
                self.assertEqual(match["storefront"], expected_storefront)
                self.assertEqual(calls, [expected_storefront])

    def test_native_script_lookup_falls_back_to_the_next_storefront(self):
        calls = []

        def regional_get(*_args, **kwargs):
            storefront = kwargs.get("params", {}).get("country")
            calls.append(storefront)
            if storefront == "HK":
                return _Response({"results": [{
                    "trackName": "漫步香港1999",
                    "artistName": "Local Artist",
                }]})
            return _Response({"results": []})

        match = fetch_itunes_preview("漫步香港1999", http_get=regional_get)
        self.assertEqual(match["track_name"], "漫步香港1999")
        self.assertEqual(match["storefront"], "HK")
        self.assertEqual(calls, ["TW", "HK"])

    def test_native_script_cache_uses_unicode_normalization(self):
        calls = []

        def counted_get(*_args, **_kwargs):
            calls.append(True)
            return _Response({"results": [{
                "trackName": "ตั้งใจจะโสด",
                "artistName": "Local Artist",
            }]})

        clear_itunes_preview_cache()
        with patch("requests.get", side_effect=counted_get):
            first = fetch_itunes_preview("ตั้งใจจะโสด")
            second = fetch_itunes_preview("  ตั้งใจจะโสด  ")

        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    def test_campaign_track_catalog_status_does_not_call_blank_placeholders_invalid(self):
        self.assertEqual(campaign_track_catalog_status("")["status"], "blank")
        self.assertEqual(campaign_track_catalog_status("Not specified")["status"], "blank")

    def test_campaign_track_catalog_status_is_unconfirmed_on_no_match_or_lookup_failure(self):
        def no_match(*_args, **_kwargs):
            return _Response({"results": []})

        def lookup_failure(*_args, **_kwargs):
            raise RuntimeError("catalog unavailable")

        self.assertEqual(
            campaign_track_catalog_status("Misspelled Song", http_get=no_match)["status"],
            "unconfirmed",
        )
        self.assertEqual(
            campaign_track_catalog_status("Regional Song", http_get=lookup_failure)["status"],
            "unconfirmed",
        )

    def test_export_fields_are_present(self):
        result = {
            "creative_type": ["Movie/Tv/Drama Edits"],
            "drama_type": "General Drama",
            "edit_focus": "General Drama Edit",
            "drama_format": "Fan Edit",
            "country_region": "Korea",
            "drama_title": "Unknown",
            "detected_audio": "Unknown",
            "campaign_song_match": "Unknown",
            "audio_version": "Unknown",
        }
        self.assertEqual(set(drama_export_values(result)), set(DRAMA_EXPORT_COLUMNS))

    def test_marketing_export_keeps_drama_details_only_in_content_details(self):
        self.assertIn("Content Details", MARKETING_EXPORT_COLUMNS)
        for column in DRAMA_EXPORT_COLUMNS:
            self.assertNotIn(column, MARKETING_EXPORT_COLUMNS)

    def test_prompt_distinguishes_story_from_cp_and_region_from_market(self):
        prompt = build_drama_prompt(
            {"narrative": "drama edit", "content_details": "A scene montage."},
            {"_campaign_market": "TH"},
        )
        self.assertIn("REAL actors", prompt)
        self.assertIn("never the uploader market", prompt)
        self.assertIn("Do not call a fictional scene a CP edit", prompt)
        self.assertIn("A male-female romantic pair must never be labelled BL or GL", prompt)
        self.assertIn("Actor/Actress Carousel", prompt)

    def test_app_has_no_drama_mode_selector(self):
        app_text = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("Drama / Creator Core", app_text)
        self.assertNotIn("tagging_focus", app_text)
        self.assertIn('"Artist name (optional)"', app_text)
        self.assertIn("songs share the same title", app_text)
        self.assertIn('"Content category (max 2)"', app_text)

    def test_backend_applies_generic_audio_default_after_waveform_check(self):
        backend_text = Path("ugc_tagger/final_update2_backend_source.py").read_text(encoding="utf-8")
        comparison_call = backend_text.index(
            "enriched = apply_audio_comparison(enriched, audio_comparison)"
        )
        default_call = backend_text.index(
            "enriched = apply_generic_original_audio_default(enriched, row)"
        )
        review_call = backend_text.index(
            "enriched = route_unknown_drama_audio_to_review(enriched, row)"
        )
        self.assertLess(comparison_call, default_call)
        self.assertLess(default_call, review_call)

    def test_resolved_kpop_show_cut_clears_stale_low_confidence_review(self):
        from ugc_tagger.drama_analysis import clear_resolved_drama_soft_review_flags

        resolved = clear_resolved_drama_soft_review_flags({
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["K-pop Show Cut"],
            "country_region": "Korea",
            "needs_human_review": True,
            "review_risk_reasons": "AI confidence below 80% (70%)",
        })
        self.assertFalse(resolved["needs_human_review"])
        self.assertEqual(resolved["review_risk_reasons"], "")

    def test_resolved_drama_clears_only_generic_subtype_review(self):
        from ugc_tagger.drama_analysis import clear_resolved_drama_soft_review_flags

        resolved = clear_resolved_drama_soft_review_flags({
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["Drama Edit"],
            "drama_type": "General Drama",
            "edit_focus": "Fictional Story",
            "drama_format": "Long-form Drama",
            "country_region": "China",
            "needs_human_review": True,
            "review_risk_reasons": (
                "Possible drama or entertainment subtype needs human confirmation"
            ),
        })
        self.assertFalse(resolved["needs_human_review"])

    def test_audio_conflict_and_routine_audit_are_never_cleared(self):
        from ugc_tagger.drama_analysis import clear_resolved_drama_soft_review_flags

        reasons = (
            "AI confidence below 80% (70%) | "
            "Drama audio comparison is close or contradictory and requires review | "
            "Routine 5% quality-audit sample"
        )
        resolved = clear_resolved_drama_soft_review_flags({
            "creative_type": ["Movie/Tv/Drama Edits"],
            "content_categories": ["K-pop Show Cut"],
            "country_region": "Korea",
            "needs_human_review": True,
            "review_risk_reasons": reasons,
        })
        self.assertTrue(resolved["needs_human_review"])
        self.assertNotIn("AI confidence below 80%", resolved["review_risk_reasons"])
        self.assertIn("audio comparison", resolved["review_risk_reasons"])
        self.assertIn("Routine 5%", resolved["review_risk_reasons"])


if __name__ == "__main__":
    unittest.main()
