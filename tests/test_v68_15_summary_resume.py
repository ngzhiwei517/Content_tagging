import ast
import json
import re
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def load_function(name, namespace):
    node = next(
        item for item in APP_TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace[name]


class RuntimeCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {"pd": pd, "json": json, "Dict": Dict}
        cls.to_payload = staticmethod(load_function("_checkpoint_dataframe_to_payload_v68_15", namespace))
        cls.from_payload = staticmethod(load_function("_checkpoint_dataframe_from_payload_v68_15", namespace))

    def test_dataframe_checkpoint_round_trip_preserves_rows_and_index(self):
        original = pd.DataFrame(
            [{"Link": "https://www.tiktok.com/@creator/video/7001", "Views": 1234}],
            index=[7],
        )
        restored = self.from_payload(self.to_payload(original))
        self.assertEqual(restored.index.tolist(), [7])
        self.assertEqual(restored.loc[7, "Link"], original.loc[7, "Link"])
        self.assertEqual(int(restored.loc[7, "Views"]), 1234)

    def test_checkpoint_contract_excludes_api_secrets(self):
        checkpoint_block = APP_SOURCE.split("RUNTIME_CHECKPOINT_STATE_KEYS_V68_15", 1)[1].split(")", 1)[0]
        self.assertNotIn("gemini_key", checkpoint_block)
        self.assertNotIn("apify_token", checkpoint_block)
        self.assertIn('"batch_df"', checkpoint_block)
        self.assertIn('"tagged_df"', checkpoint_block)

    def test_url_tracks_batch_and_step_for_reconnect(self):
        self.assertIn('st.query_params["run"] = run_id', APP_SOURCE)
        self.assertIn('st.query_params["step"]', APP_SOURCE)
        self.assertIn("Your previous batch was restored after reconnecting.", APP_SOURCE)


class SummaryV6815Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {"pd": pd, "List": List, "re": re}
        for name in [
            "safe_str",
            "clean_num",
            "rate_pct",
            "unavailable_metric_names",
            "metric_is_available",
            "available_metric_rate",
        ]:
            namespace[name] = load_function(name, namespace)
        cls.aggregate = staticmethod(load_function("aggregate_summary_performance_v68_15", namespace))
        cls.summary_sort_column = staticmethod(load_function("summary_sort_column_v68_15", namespace))
        namespace["summary_sort_column_v68_15"] = cls.summary_sort_column
        cls.sort_summary = staticmethod(load_function("sort_summary_performance_v68_18", namespace))
        namespace["Optional"] = __import__("typing").Optional
        namespace["SUMMARY_INTEGER_COLUMNS_V68_46"] = {
            "Posts", "Followers", "Views", "Likes", "Comments", "Shares",
            "Saves", "Total Engagement", "Total Views", "Average Views", "Average Engagements",
        }
        namespace["SUMMARY_PERCENT_COLUMNS_V68_46"] = {
            "Engagement Rate", "Average Engagement Rate", "Likes Rate",
            "Comments Rate", "Shares Rate", "Saves Rate",
        }
        namespace["TOP_POST_TABLE_COLUMNS_V68_46"] = [
            "Platform", "Creator", "Market", "Track", "Creative Type",
            "Followers", "KOL Size", "Views", "Total Engagement",
            "Engagement Rate", "Link",
        ]
        cls.prepare_summary_table = staticmethod(load_function("prepare_sortable_summary_table_v68_46", namespace))
        namespace["prepare_sortable_summary_table_v68_46"] = cls.prepare_summary_table
        cls.prepare_top_posts = staticmethod(load_function("prepare_sortable_top_posts_v68_46", namespace))
        namespace["Tuple"] = Tuple
        namespace["TIKTOK"] = "TikTok"
        namespace["display_empty"] = lambda value, fallback="Not specified": namespace["safe_str"](value) or fallback
        namespace["display_market"] = lambda value: namespace["safe_str"](value) or "Other"
        cls.creator_summary = staticmethod(load_function("creator_performance_summary_v68_47", namespace))

    def test_group_summary_uses_average_engagement_metrics(self):
        rows = pd.DataFrame([
            {"Market": "MY", "Link": "a", "Views": 1000, "Likes": 100, "Comments": 0, "Shares": 0, "Saves": 0, "Total Engagement": 100, "Engagement Rate": 10.0},
            {"Market": "MY", "Link": "b", "Views": 1000, "Likes": 300, "Comments": 0, "Shares": 0, "Saves": 0, "Total Engagement": 300, "Engagement Rate": 30.0},
        ])
        summary = self.aggregate(rows, ["Market"])
        self.assertEqual(float(summary.loc[0, "Average_Views"]), 1000.0)
        self.assertEqual(float(summary.loc[0, "Average_Engagements"]), 200.0)
        self.assertEqual(float(summary.loc[0, "Average_Engagement_Rate"]), 20.0)
        self.assertEqual(float(summary.loc[0, "Average_Shares_Rate"]), 0.0)
        self.assertEqual(float(summary.loc[0, "Average_Saves_Rate"]), 0.0)

    def test_group_tables_keep_full_average_performance_columns(self):
        for column in [
            '"Average Views"',
            '"Average Engagements"',
            '"Average Engagement Rate"',
            '"Shares Rate"',
            '"Saves Rate"',
        ]:
            self.assertIn(column, APP_SOURCE)

    def test_summary_has_requested_order_and_no_median_metric(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        positions = [
            step_six.index('section_title("Market Summary"'),
            step_six.index('section_title("Track Summary"'),
            step_six.index('section_title("Creative Type Mix"'),
            step_six.index('section_title("Top Posts"'),
            step_six.index("render_top_creator_performance_v68_47(filtered)"),
            step_six.index('section_title("Downloads"'),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Median Engagement Rate", APP_SOURCE)

    def test_tiktok_links_render_as_safe_clickable_links(self):
        self.assertIn('target="_blank"', APP_SOURCE)
        self.assertIn('rel="noopener noreferrer"', APP_SOURCE)
        self.assertIn(">Open TikTok</a>", APP_SOURCE)

    def test_empty_filtered_summary_does_not_choose_a_missing_sort_column(self):
        empty = self.aggregate(pd.DataFrame(), ["Track"])
        self.assertTrue(empty.empty)
        self.assertEqual(self.summary_sort_column("Views", empty.columns), "")
        sorted_empty = self.sort_summary(empty, "Views", "Highest first")
        self.assertTrue(sorted_empty.empty)

    def test_summary_sort_falls_back_only_to_an_available_column(self):
        columns = ["Track", "Posts", "Average Engagements"]
        self.assertEqual(
            self.summary_sort_column("Followers", columns),
            "Average Engagements",
        )

    def test_top_posts_keep_numeric_columns_for_header_sorting(self):
        rows = pd.DataFrame([
            {
                "Platform": "TikTok", "Creator": "a", "Market Display": "MY",
                "Track Display": "Song", "Creative Type": "Performance",
                "Followers": "41,700", "KOL Size": "Micro", "Views": "8,300,000",
                "Total Engagement": "84,583", "Link": "https://example.com/a",
            },
            {
                "Platform": "TikTok", "Creator": "b", "Market Display": "SG",
                "Track Display": "Song", "Creative Type": "Dance",
                "Followers": "51,500", "KOL Size": "Macro", "Views": "8,200,000",
                "Total Engagement": "61,659", "Link": "https://example.com/b",
            },
        ])
        top_posts = self.prepare_top_posts(rows)
        self.assertEqual(top_posts["Views"].tolist(), [8_300_000, 8_200_000])
        self.assertIn(top_posts["Views"].dtype.kind, "iu")
        self.assertIn(top_posts["Followers"].dtype.kind, "iu")
        self.assertIn(top_posts["Total Engagement"].dtype.kind, "iu")
        self.assertIn(top_posts["Engagement Rate"].dtype.kind, "f")
        self.assertEqual(top_posts.iloc[0]["Market"], "MY")
        self.assertEqual(top_posts.iloc[0]["Link"], "https://example.com/a")

    def test_top_posts_use_native_clickable_header_table(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        top_posts_block = step_six.split('section_title("Top Posts"', 1)[1].split(
            "render_top_creator_performance_v68_47", 1
        )[0]
        self.assertIn("render_sortable_summary_table_v68_46(", top_posts_block)
        self.assertIn("st.dataframe(", APP_SOURCE)
        self.assertIn("st.column_config.NumberColumn", APP_SOURCE)
        self.assertIn("st.column_config.LinkColumn", APP_SOURCE)

    def test_every_summary_table_uses_clickable_header_sorting(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        for title in ["Platform Summary", "Market Summary", "Track Summary", "Source Summary"]:
            with self.subTest(title=title):
                section = step_six.split(f'section_title("{title}"', 1)[1]
                self.assertIn("render_sortable_summary_table_v68_46(", section)
        creator_function = APP_SOURCE.split("def render_top_creator_performance_v68_47", 1)[1].split(
            "def bar_list", 1
        )[0]
        self.assertIn("render_sortable_summary_table_v68_46(", creator_function)

    def test_creator_performance_groups_handles_and_uses_weighted_engagement(self):
        rows = pd.DataFrame([
            {
                "Platform": "TikTok", "Market": "SG", "Creator": "@Alice", "Link": "a",
                "Views": 1_000, "Likes": 80, "Comments": 10, "Shares": 5, "Saves": 5,
                "Total Engagement": 9_999, "Followers": 10_000, "KOL Size": "Micro",
            },
            {
                "Platform": "TikTok", "Market": "SG", "Creator": "alice", "Link": "b",
                "Views": 100, "Likes": 10, "Comments": 5, "Shares": 3, "Saves": 2,
                "Total Engagement": 9_999, "Followers": 12_000, "KOL Size": "Micro",
            },
        ])
        summary, missing = self.creator_summary(rows)
        self.assertEqual(missing, 0)
        self.assertEqual(len(summary), 1)
        self.assertEqual(int(summary.loc[0, "Posts"]), 2)
        self.assertEqual(int(summary.loc[0, "Followers"]), 12_000)
        self.assertEqual(int(summary.loc[0, "Total Views"]), 1_100)
        self.assertEqual(int(summary.loc[0, "Total Engagement"]), 120)
        self.assertAlmostEqual(float(summary.loc[0, "Engagement Rate"]), 120 / 1_100 * 100)

    def test_creator_performance_ranks_engagement_and_keeps_market_platform_separate(self):
        rows = pd.DataFrame([
            {"Platform": "TikTok", "Market": "SG", "Creator": "Alice", "Views": 100, "Likes": 10},
            {"Platform": "Instagram Reels", "Market": "MY", "Creator": "Alice", "Views": 200, "Likes": 20},
            {"Platform": "TikTok", "Market": "SG", "Creator": "Bob", "Views": 500, "Likes": 80},
            {"Platform": "TikTok", "Market": "SG", "Creator": "", "Views": 900, "Likes": 500},
            {"Platform": "TikTok", "Market": "SG", "Creator": "@", "Views": 900, "Likes": 500},
        ])
        summary, missing = self.creator_summary(rows)
        self.assertEqual(missing, 2)
        self.assertEqual(summary["Creator"].tolist()[0], "Bob")
        self.assertEqual(len(summary[summary["Creator"].str.casefold() == "alice"]), 2)

    def test_creator_performance_falls_back_to_supplied_total_when_components_are_missing(self):
        summary, _ = self.creator_summary(pd.DataFrame([{
            "Platform": "TikTok", "Market": "PH", "Creator": "Creator A",
            "Views": 1_000, "Total Engagement": 75,
        }]))
        self.assertEqual(int(summary.loc[0, "Total Engagement"]), 75)
        self.assertAlmostEqual(float(summary.loc[0, "Engagement Rate"]), 7.5)

    def test_group_summary_metrics_remain_numeric_for_header_sorting(self):
        table = self.prepare_summary_table(
            pd.DataFrame([{
                "Track": "Song", "Posts": "2", "Average Views": "1,100,000",
                "Average Engagements": "66,000", "Average Engagement Rate": "6.00%",
                "Shares Rate": "0.21%", "Saves Rate": "0.33%",
            }]),
            ["Track", "Posts", "Average Views", "Average Engagements", "Average Engagement Rate", "Shares Rate", "Saves Rate"],
        )
        for column in ["Posts", "Average Views", "Average Engagements"]:
            self.assertIn(table[column].dtype.kind, "iu")
        for column in ["Average Engagement Rate", "Shares Rate", "Saves Rate"]:
            self.assertIn(table[column].dtype.kind, "f")


if __name__ == "__main__":
    unittest.main()
