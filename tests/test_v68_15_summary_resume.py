import ast
import json
import re
import unittest
from pathlib import Path
from typing import Dict, List

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
            step_six.index("render_kol_size_performance_v68_15(filtered, market_filter)"),
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


if __name__ == "__main__":
    unittest.main()
