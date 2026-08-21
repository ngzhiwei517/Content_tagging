from datetime import datetime, timezone
import unittest

from ugc_tagger.melodyiq_status import (
    elapsed_seconds,
    format_elapsed,
    preparation_estimate,
)


class MelodyIQStatusTests(unittest.TestCase):
    def test_preparation_estimate_uses_broad_volume_bands(self):
        cases = (
            (1, "5–20 minutes"),
            (50_000, "15–60 minutes"),
            (250_000, "30 minutes–2 hours"),
            (750_000, "1–4 hours"),
            (2_396_358, "2–8+ hours"),
        )
        for post_count, expected in cases:
            with self.subTest(post_count=post_count):
                self.assertEqual(preparation_estimate(post_count)[0], expected)

    def test_missing_post_count_does_not_invent_an_estimate(self):
        self.assertEqual(
            preparation_estimate(None),
            ("Waiting for tracked-post count", None),
        )

    def test_elapsed_seconds_accepts_utc_iso_timestamp(self):
        now = datetime(2026, 8, 21, 8, 30, tzinfo=timezone.utc)

        result = elapsed_seconds("2026-08-21T06:15:00Z", now=now)

        self.assertEqual(result, 8_100)
        self.assertEqual(format_elapsed(result), "2 hr 15 min")

    def test_invalid_timestamp_degrades_safely(self):
        self.assertIsNone(elapsed_seconds("not-a-time"))
        self.assertEqual(format_elapsed(None), "Starting")


if __name__ == "__main__":
    unittest.main()
