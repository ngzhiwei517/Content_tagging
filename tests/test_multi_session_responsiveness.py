import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class MultiSessionResponsivenessTests(unittest.TestCase):
    def test_local_tagging_yields_after_two_completed_posts(self):
        self.assertIn(
            "MAX_LIVE_POSTS_PER_EXECUTION_V68_52 = 2",
            APP_SOURCE,
        )

    def test_recovery_link_warns_against_separate_users_sharing_one_batch(self):
        self.assertIn(
            '"This recovery link opens one saved batch.',
            APP_SOURCE,
        )
        self.assertIn('"Start a separate batch"', APP_SOURCE)
        self.assertIn("_start_separate_batch_v68_104()", APP_SOURCE)

    def test_separate_batch_gets_a_new_recovery_id(self):
        helper = APP_SOURCE.split(
            "def _start_separate_batch_v68_104()",
            1,
        )[1].split("# Display values and engagement metrics", 1)[0]
        self.assertIn("_new_runtime_recovery_id_v68_44()", helper)

    def test_track_catalog_lookup_is_explicit_instead_of_running_on_upload(self):
        helper = APP_SOURCE.split(
            "def render_uploaded_track_catalog_feedback_v68_62(",
            1,
        )[1].split("CREATOR_PROFILE_CACHE_TTL_SECONDS_V68_61", 1)[0]
        self.assertIn('"Confirm track now (optional)"', helper)
        self.assertIn(
            '"still check the official audio automatically during tagging."',
            helper,
        )
        self.assertIn("if st.button(", helper)
        self.assertLess(
            helper.index("if st.button("),
            helper.index("campaign_track_catalog_status_v68_36("),
        )
        paste_section = APP_SOURCE.split("with paste_tab:", 1)[1].split(
            'st.markdown("</div>"',
            1,
        )[0]
        self.assertIn(
            "resolved_paste_artist = render_uploaded_track_catalog_feedback_v68_62(",
            paste_section,
        )


if __name__ == "__main__":
    unittest.main()
