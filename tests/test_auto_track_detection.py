import unittest
from pathlib import Path

from final_update2_adapter import _record_music_name, _resolved_campaign_track


class AutoTrackDetectionTests(unittest.TestCase):
    def test_blank_pasted_track_uses_tiktok_music_name(self):
        record = {"musicMeta": {"musicName": "ตั้งใจจะโสด", "musicAuthor": "RachYo"}}
        self.assertEqual(_record_music_name(record), "ตั้งใจจะโสด")
        self.assertEqual(_resolved_campaign_track({"Track": ""}, record), "ตั้งใจจะโสด")

    def test_uploaded_track_remains_authoritative(self):
        record = {"musicMeta": {"musicName": "TikTok remix"}}
        self.assertEqual(
            _resolved_campaign_track({"Track": "Campaign master"}, record),
            "Campaign master",
        )

    def test_optional_campaign_artist_disambiguates_the_track_without_changing_the_title(self):
        record = {"musicMeta": {"musicName": "TikTok remix"}}
        self.assertEqual(
            _resolved_campaign_track(
                {"Track": "Hit the Wall", "Campaign Artist": "Gracie Abrams"},
                record,
            ),
            "Gracie Abrams - Hit the Wall",
        )

    def test_existing_artist_track_value_is_not_prefixed_twice(self):
        self.assertEqual(
            _resolved_campaign_track(
                {"Track": "Gracie Abrams - Hit the Wall", "Campaign Artist": "Gracie Abrams"},
                {},
            ),
            "Gracie Abrams - Hit the Wall",
        )

    def test_top_level_music_name_is_supported(self):
        self.assertEqual(
            _resolved_campaign_track({"Track": ""}, {"musicName": "Detected song"}),
            "Detected song",
        )

    def test_pasted_link_ui_keeps_manual_campaign_track_override(self):
        app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Campaign track / sound name (optional)"', app_source)
        self.assertIn('"Artist name (optional)"', app_source)
        self.assertIn('"Track": safe_str(paste_track)', app_source)
        self.assertIn('"Campaign Artist": safe_str(paste_artist)', app_source)

    def test_track_information_note_precedes_pasted_track_input_and_explains_artist_disambiguation(self):
        app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8"
        )
        paste_section = app_source[app_source.index("with paste_tab:"):]
        self.assertLess(
            paste_section.index('st.info(drama_audio_note'),
            paste_section.index('"Campaign track / sound name (optional)"'),
        )
        self.assertIn("fill in the optional Artist field", paste_section)
        self.assertIn("campaign_track_lookup", paste_section)


if __name__ == "__main__":
    unittest.main()
