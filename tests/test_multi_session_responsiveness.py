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


if __name__ == "__main__":
    unittest.main()
