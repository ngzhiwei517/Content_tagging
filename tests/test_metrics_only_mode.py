import inspect
import unittest
from pathlib import Path

import pandas as pd

from ugc_tagger.final_update2_adapter import metrics_candidates


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class MetricsOnlyAdapterTests(unittest.TestCase):
    TIKTOK_URL = "https://www.tiktok.com/@creator/video/7654321000000000001"
    INSTAGRAM_URL = "https://www.instagram.com/reel/DExampleAbC1/"

    def test_refreshes_metrics_and_calculates_engagement_without_ai(self):
        candidates = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Link": self.TIKTOK_URL,
                "Market": "SG",
                "Track": "Example Track",
            }
        ])
        records = [{
            "id": "7654321000000000001",
            "webVideoUrl": self.TIKTOK_URL,
            "playCount": 1_000,
            "diggCount": 100,
            "commentCount": 20,
            "shareCount": 10,
            "collectCount": 5,
            "authorMeta": {"name": "creator", "fans": 12_345},
        }]

        result = metrics_candidates(candidates, records)

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["Views"], 1_000)
        self.assertEqual(row["Likes"], 100)
        self.assertEqual(row["Comments"], 20)
        self.assertEqual(row["Shares"], 10)
        self.assertEqual(row["Saves"], 5)
        self.assertEqual(row["Total Engagement"], 135)
        self.assertEqual(row["Engagement Rate"], 13.5)
        self.assertEqual(row["Followers"], 12_345)
        self.assertEqual(row["Metrics Status"], "Refreshed")
        self.assertFalse(bool(row["Gemini Called"]))
        self.assertEqual(row["Validation Status"], "metrics_only")

    def test_missing_values_remain_blank_instead_of_false_zero(self):
        candidates = pd.DataFrame([
            {"Platform": "TikTok", "Link": self.TIKTOK_URL}
        ])
        records = [{
            "id": "7654321000000000001",
            "webVideoUrl": self.TIKTOK_URL,
            "playCount": 0,
            "diggCount": 0,
            "commentCount": 0,
        }]

        row = metrics_candidates(candidates, records).iloc[0]

        self.assertEqual(row["Views"], 0)
        self.assertEqual(row["Likes"], 0)
        self.assertEqual(row["Comments"], 0)
        self.assertTrue(pd.isna(row["Shares"]))
        self.assertTrue(pd.isna(row["Saves"]))
        self.assertEqual(row["Metrics Status"], "Partial")
        self.assertIn("Shares", row["Metrics Unavailable"])
        self.assertIn("Saves", row["Metrics Unavailable"])

    def test_instagram_unavailable_metrics_are_not_reported_as_zero(self):
        candidates = pd.DataFrame([
            {"Platform": "Instagram Reels", "Link": self.INSTAGRAM_URL}
        ])
        records = [{
            "id": "DExampleAbC1",
            "url": self.INSTAGRAM_URL,
            "playCount": 2_000,
            "diggCount": 120,
            "commentCount": 30,
            "instagramMetricsUnavailable": ["Shares", "Saves"],
        }]

        row = metrics_candidates(candidates, records).iloc[0]

        self.assertEqual(row["Total Engagement"], 150)
        self.assertEqual(row["Engagement Rate"], 7.5)
        self.assertTrue(pd.isna(row["Shares"]))
        self.assertTrue(pd.isna(row["Saves"]))
        self.assertEqual(row["Metrics Status"], "Partial")

    def test_missing_record_is_marked_not_refreshed(self):
        candidates = pd.DataFrame([
            {"Platform": "TikTok", "Link": self.TIKTOK_URL}
        ])

        row = metrics_candidates(candidates, []).iloc[0]

        self.assertEqual(row["Metrics Status"], "Not refreshed")
        self.assertTrue(pd.isna(row["Views"]))
        self.assertTrue(pd.isna(row["Total Engagement"]))
        self.assertFalse(bool(row["Gemini Called"]))


class MetricsOnlyUiContractTests(unittest.TestCase):
    def test_add_posts_page_offers_metrics_only_and_run_page_uses_selection(self):
        step_two = APP_SOURCE.split("# STEP 2: Add posts", 1)[1].split(
            "# STEP 3: Select posts",
            1,
        )[0]
        step_four = APP_SOURCE.split("# STEP 4: Run tagging", 1)[1].split(
            "# STEP 5: Review",
            1,
        )[0]
        step_six = APP_SOURCE.split("# STEP 6: Summary and export", 1)[1]

        self.assertIn('"What do you want to run?"', step_two)
        self.assertIn('["AI tagging", "Metrics only"]', APP_SOURCE)
        self.assertNotIn('"What do you want to run?"', step_four)
        self.assertIn('st.session_state.get("analysis_mode_v68_86")', step_four)
        self.assertIn('run_page_title_v68_86 = "Fetch metrics"', step_four)
        self.assertIn('metrics_button_label_v68_86 = "Fetch metrics"', step_four)
        self.assertIn("if metrics_complete_v68_86:", step_four)
        self.assertIn("go(6)", step_four)
        self.assertNotIn('"Download metrics CSV"', step_four)
        self.assertIn("<h2>Metrics & Export</h2>", step_six)
        self.assertIn('"Download metrics CSV"', step_six)
        self.assertIn('"Download metrics Excel"', step_six)

    def test_metrics_export_branch_skips_tagged_summary(self):
        step_six = APP_SOURCE.split("# STEP 6: Summary and export", 1)[1]
        metrics_branch = step_six.split("tagged = st.session_state.tagged_df", 1)[0]

        self.assertIn("metrics_only_export_mode_v68_86", metrics_branch)
        self.assertIn("st.stop()", metrics_branch)
        self.assertIn('"Refresh metrics"', metrics_branch)
        self.assertIn('"Start new batch"', metrics_branch)

    def test_metrics_helper_is_loaded_safely_during_hot_reload(self):
        import_block = APP_SOURCE.split(
            "from ugc_tagger.final_update2_adapter import (",
            1,
        )[1].split(")", 1)[0]
        wrapper = APP_SOURCE.split(
            "def final_update2_metrics_candidates(",
            1,
        )[1].split("def _failed_analysis_review_row_v68_43", 1)[0]

        self.assertNotIn("metrics_candidates", import_block)
        self.assertIn('getattr(adapter, "metrics_candidates", None)', wrapper)
        self.assertIn("importlib.reload(adapter)", wrapper)

    def test_metrics_runner_never_calls_tagging_backend(self):
        runner = APP_SOURCE.split(
            "def _run_metrics_only_chunk_v68_86",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertIn("final_update2_scrape_links(", runner)
        self.assertIn("final_update2_metrics_candidates(", runner)
        self.assertNotIn("final_update2_tag_candidates(", runner)
        self.assertNotIn("gemini_key", runner.casefold())
        self.assertNotIn("load_backend", runner.casefold())

    def test_adapter_function_contains_no_ai_backend_call(self):
        source = inspect.getsource(metrics_candidates).casefold()
        self.assertNotIn("load_backend", source)
        self.assertNotIn("tag_candidates", source)

    def test_metrics_state_is_restart_safe(self):
        state_keys = APP_SOURCE.split(
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15 = (",
            1,
        )[1].split(")", 1)[0]
        frame_keys = APP_SOURCE.split(
            "RUNTIME_DATAFRAME_KEYS_V68_15 = {",
            1,
        )[1].split("}", 1)[0]
        self.assertIn('"metrics_only_active_v68_86"', state_keys)
        self.assertIn('"metrics_only_next_position_v68_86"', state_keys)
        self.assertIn('"metrics_only_fingerprint_v68_86"', state_keys)
        self.assertIn('"metrics_only_df_v68_86"', frame_keys)

    def test_metrics_scraping_is_limited_to_safe_windows(self):
        runner = APP_SOURCE.split(
            "def _run_metrics_only_chunk_v68_86",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertIn("start + MAX_APIFY_POSTS_PER_REQUEST", runner)


if __name__ == "__main__":
    unittest.main()
