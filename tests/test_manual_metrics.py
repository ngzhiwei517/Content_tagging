import unittest

import pandas as pd

from ugc_tagger.manual_metrics import (
    build_manual_metric_updates,
    missing_metric_names,
    parse_manual_metric,
)


class ManualMetricParsingTests(unittest.TestCase):
    def test_blank_is_unavailable_and_zero_is_valid(self):
        self.assertIsNone(parse_manual_metric(""))
        self.assertIsNone(parse_manual_metric("Not available"))
        self.assertEqual(parse_manual_metric("0"), 0)

    def test_common_count_formats_are_supported(self):
        self.assertEqual(parse_manual_metric("1,234"), 1234)
        self.assertEqual(parse_manual_metric("1.2K"), 1200)
        self.assertEqual(parse_manual_metric("2.5M"), 2_500_000)

    def test_invalid_or_fractional_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_manual_metric("about 100")
        with self.assertRaises(ValueError):
            parse_manual_metric("1.25")


class MissingMetricTests(unittest.TestCase):
    def test_explicit_unavailable_metrics_are_returned(self):
        row = {
            "Views": 100,
            "Likes": 10,
            "Comments": 2,
            "Shares": pd.NA,
            "Saves": pd.NA,
            "Metrics Unavailable": "Shares, Saves",
        }
        self.assertEqual(missing_metric_names(row), ["Shares", "Saves"])

    def test_real_zero_is_not_treated_as_missing(self):
        row = {
            "Views": 100,
            "Likes": 0,
            "Comments": 0,
            "Shares": 0,
            "Saves": 0,
            "Metrics Unavailable": "",
        }
        self.assertEqual(missing_metric_names(row), [])

    def test_exception_zero_counts_are_treated_as_missing(self):
        row = {
            "Views": 0,
            "Likes": 0,
            "Comments": 0,
            "Shares": 0,
            "Saves": 0,
            "Tier Used": "scraper_exception",
        }
        self.assertEqual(
            missing_metric_names(row),
            ["Views", "Likes", "Comments", "Shares", "Saves"],
        )


class ManualMetricUpdateTests(unittest.TestCase):
    def test_only_entered_missing_metrics_are_filled_and_audited(self):
        row = {
            "Views": 100,
            "Likes": 10,
            "Comments": 2,
            "Shares": pd.NA,
            "Saves": pd.NA,
            "Metrics Unavailable": "Shares, Saves",
        }
        updates = build_manual_metric_updates(
            row,
            {"Shares": "1.2K", "Saves": ""},
            captured_at="2026-07-24T10:00:00+00:00",
        )
        self.assertEqual(updates["Shares"], 1200)
        self.assertIsNone(updates["Saves"])
        self.assertEqual(updates["Metrics Unavailable"], "Saves")
        self.assertEqual(updates["Manual Metrics Source"], "Manual review")
        self.assertEqual(updates["Manual Metrics Fields"], "Shares")
        self.assertEqual(
            updates["Manual Metrics Captured At"],
            "2026-07-24T10:00:00+00:00",
        )

    def test_all_blank_inputs_remain_unavailable_without_a_fake_audit(self):
        row = {
            "Views": pd.NA,
            "Likes": pd.NA,
            "Comments": pd.NA,
            "Shares": pd.NA,
            "Saves": pd.NA,
            "Metrics Unavailable": "Views, Likes, Comments, Shares, Saves",
        }
        updates = build_manual_metric_updates(row, {})
        self.assertEqual(
            updates["Metrics Unavailable"],
            "Views, Likes, Comments, Shares, Saves",
        )
        self.assertTrue(
            all(
                updates[name] is None
                for name in ["Views", "Likes", "Comments", "Shares", "Saves"]
            )
        )
        self.assertNotIn("Manual Metrics Source", updates)
        self.assertNotIn("Manual Metrics Captured At", updates)


if __name__ == "__main__":
    unittest.main()
