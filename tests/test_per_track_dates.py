import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)
DATE_SCOPE_SHARED = "Same date for all tracks"
DATE_SCOPE_PER_TRACK = "Different date by track"


def load_function(name, namespace):
    node = next(
        item for item in APP_TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace[name]


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class PerTrackDateHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {"pd": pd, "Optional": Optional, "Dict": Dict}
        cls.filter_dates = staticmethod(load_function("filter_posts_by_date_window_v68", namespace))

    def test_global_window_remains_inclusive(self):
        rows = pd.DataFrame({"Name": ["start", "end", "outside"]})
        dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-08", "2026-01-09"]))
        result = self.filter_dates(rows, dates, 7, global_date="2026-01-01")
        self.assertEqual(result["Name"].tolist(), ["start", "end"])

    def test_tracks_use_independent_dates(self):
        rows = pd.DataFrame({
            "Track Display": ["A", "A", "B", "B"],
            "Name": ["A in", "A out", "B in", "B out"],
        })
        dates = pd.Series(pd.to_datetime(["2026-01-03", "2026-02-03", "2026-03-03", "2026-04-03"]))
        result = self.filter_dates(rows, dates, 7, track_settings={
            "A": {"enabled": True, "date": "2026-01-01"},
            "B": {"enabled": True, "date": "2026-03-01"},
        })
        self.assertEqual(result["Name"].tolist(), ["A in", "B in"])

    def test_disabled_nonviral_track_is_not_filtered(self):
        rows = pd.DataFrame({
            "Track Display": ["A", "A", "B"],
            "Name": ["A in", "A out", "B unchanged"],
        })
        dates = pd.Series(pd.to_datetime(["2026-01-03", "2026-02-03", "2026-12-31"]))
        result = self.filter_dates(rows, dates, 7, track_settings={
            "A": {"enabled": True, "date": "2026-01-01"},
            "B": {"enabled": False, "date": "2026-03-01"},
        })
        self.assertEqual(result["Name"].tolist(), ["A in", "B unchanged"])

    def test_missing_date_is_excluded_only_for_enabled_track(self):
        rows = pd.DataFrame({
            "Track Display": ["A", "B"],
            "Name": ["A missing", "B missing"],
        })
        dates = pd.Series([pd.NaT, pd.NaT])
        result = self.filter_dates(rows, dates, 7, track_settings={
            "A": {"enabled": True, "date": "2026-01-01"},
            "B": {"enabled": False, "date": "2026-03-01"},
        })
        self.assertEqual(result["Name"].tolist(), ["B missing"])


class PerTrackDateSelectionTests(unittest.TestCase):
    def setUp(self):
        self.state = SessionState({
            "use_date_filter": True,
            "date_filter_scope_v68": DATE_SCOPE_PER_TRACK,
            "track_date_settings_v68": {
                "A": {"enabled": True, "date": "2026-01-01"},
                "B": {"enabled": True, "date": "2026-03-01"},
            },
            "date_window": 7,
            "selection_mode": "Top posts",
            "top_n": 1,
            "rank_metrics": ["Views"],
            "group_by": "Track",
            "select_markets": ["All"],
            "select_tracks": ["All"],
            "select_sources": ["All"],
        })
        fake_st = SimpleNamespace(session_state=self.state)
        namespace = {
            "pd": pd,
            "Optional": Optional,
            "Dict": Dict,
            "st": fake_st,
            "DATE_SCOPE_SHARED": DATE_SCOPE_SHARED,
            "DATE_SCOPE_PER_TRACK": DATE_SCOPE_PER_TRACK,
            "add_performance_fields": lambda frame: frame.copy(),
            "display_market": lambda value: str(value).strip() or "Other",
            "display_empty": lambda value, fallback: str(value).strip() or fallback,
            "canonical_post_date": lambda row: pd.to_datetime(row.get("Date"), errors="coerce"),
            "clean_num": lambda value: int(float(value or 0)),
            "calculate_engagement_rate": lambda row: 0,
        }
        namespace["filter_posts_by_date_window_v68"] = load_function(
            "filter_posts_by_date_window_v68", namespace
        )
        self.preview = load_function("selected_posts_preview", namespace)
        namespace["selected_posts_preview"] = self.preview
        self.all_candidates = load_function("_all_ranked_candidates_v56", namespace)

    def sample_batch(self):
        return pd.DataFrame([
            {"Track": "A", "Market": "MY", "Source": "test", "Date": "2026-01-03", "Views": 100, "Total Engagement": 1},
            {"Track": "A", "Market": "MY", "Source": "test", "Date": "2026-02-03", "Views": 9999, "Total Engagement": 1},
            {"Track": "B", "Market": "MY", "Source": "test", "Date": "2026-03-03", "Views": 200, "Total Engagement": 1},
            {"Track": "B", "Market": "MY", "Source": "test", "Date": "2026-04-03", "Views": 9999, "Total Engagement": 1},
        ])

    def test_top_n_is_ranked_after_each_track_window(self):
        result = self.preview(self.sample_batch())
        self.assertEqual(result[["Track", "Views"]].values.tolist(), [["A", 100], ["B", 200]])

    def test_backfill_candidate_pool_stays_inside_track_windows(self):
        result = self.all_candidates(self.sample_batch())
        self.assertEqual(result[["Track", "Views"]].values.tolist(), [["A", 100], ["B", 200]])


class PerTrackDateStateAndSourceTests(unittest.TestCase):
    def test_numeric_excel_date_text_is_supported(self):
        namespace = {"pd": pd, "re": re}
        namespace["safe_str"] = load_function("safe_str", namespace)
        parser = load_function("input_post_date", namespace)
        self.assertEqual(parser("46026").date().isoformat(), "2026-01-04")
        self.assertEqual(parser("2026-03-08").date().isoformat(), "2026-03-08")

    def test_consistent_uploaded_viral_date_can_prefill_track(self):
        namespace = {"pd": pd, "re": re}
        namespace["safe_str"] = load_function("safe_str", namespace)
        namespace["input_post_date"] = load_function("input_post_date", namespace)
        infer = load_function("inferred_viral_date_for_track_v68", namespace)
        rows = pd.DataFrame({
            "Track Display": ["A", "A", "B"],
            "Viral Date": ["46026", "46026", "2026-03-08"],
        })
        self.assertEqual(infer(rows, "A").isoformat(), "2026-01-04")

    def test_new_batch_reset_removes_track_date_widgets(self):
        state = SessionState({
            "use_date_filter": True,
            "date_filter_scope_v68": DATE_SCOPE_PER_TRACK,
            "track_date_settings_v68": {"A": {"enabled": True, "date": "2026-01-01"}},
            "date_filter_scope_widget_v68": DATE_SCOPE_PER_TRACK,
            "track_date_window_widget_v68": 7,
            "track_date_enabled_v68_abc": True,
            "track_date_value_v68_abc": pd.Timestamp("2026-01-01").date(),
            "unrelated": "keep",
        })
        reset = load_function(
            "reset_date_filter_state_v68",
            {
                "st": SimpleNamespace(session_state=state),
                "DATE_SCOPE_SHARED": DATE_SCOPE_SHARED,
            },
        )
        reset()
        self.assertFalse(state["use_date_filter"])
        self.assertEqual(state["date_filter_scope_v68"], DATE_SCOPE_SHARED)
        self.assertEqual(state["track_date_settings_v68"], {})
        self.assertNotIn("track_date_enabled_v68_abc", state)
        self.assertNotIn("track_date_window_widget_v68", state)
        self.assertEqual(state["unrelated"], "keep")

    def test_ui_and_upload_contracts_are_present(self):
        for phrase in [
            "Different date by track",
            "Choose a date for each track",
            "<b>Date filter on</b>",
            "with st.container(border=True):",
            '"viral_date": detect_col',
            '"Viral Date": safe_str',
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, APP_SOURCE)
        self.assertGreaterEqual(APP_SOURCE.count("reset_date_filter_state_v68()"), 2)

    def test_date_scope_uses_stateful_primary_secondary_buttons(self):
        calls = [
            node for node in ast.walk(APP_TREE)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "segmented_control"
        ]
        self.assertEqual(calls, [])
        for phrase in [
            'key="date_scope_shared_button_v68"',
            'key="date_scope_per_track_button_v68"',
            'type="primary" if previous_scope == DATE_SCOPE_SHARED else "secondary"',
            'type="primary" if previous_scope == DATE_SCOPE_PER_TRACK else "secondary"',
            "on_click=set_date_filter_scope_v68",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, APP_SOURCE)

    def test_date_scope_button_callback_changes_persistent_state(self):
        state = SessionState({"date_filter_scope_v68": DATE_SCOPE_SHARED})
        callback = load_function(
            "set_date_filter_scope_v68",
            {
                "st": SimpleNamespace(session_state=state),
                "DATE_SCOPE_SHARED": DATE_SCOPE_SHARED,
                "DATE_SCOPE_PER_TRACK": DATE_SCOPE_PER_TRACK,
            },
        )
        callback(DATE_SCOPE_PER_TRACK)
        self.assertEqual(state["date_filter_scope_v68"], DATE_SCOPE_PER_TRACK)
        callback("invalid")
        self.assertEqual(state["date_filter_scope_v68"], DATE_SCOPE_SHARED)

    def test_qa_sort_metric_reports_actual_selection_ranking(self):
        label = load_function(
            "selection_rank_metric_label",
            {"safe_str": lambda value: str(value).strip()},
        )
        self.assertEqual(label("Top posts", ["Total Engagement"]), "Total Engagement")
        self.assertEqual(label("Top posts", ["Views", "Shares"]), "Views, Shares")
        self.assertIn('"Current Sort Metric": selection_rank_metric_label(', APP_SOURCE)

    def test_tag_every_link_records_original_order(self):
        label = load_function(
            "selection_rank_metric_label",
            {"safe_str": lambda value: str(value).strip()},
        )
        self.assertEqual(label("Tag every link", ["Views"]), "Original batch order")


if __name__ == "__main__":
    unittest.main()
