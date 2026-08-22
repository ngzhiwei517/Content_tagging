import unittest

import pandas as pd

from ugc_tagger.melodyiq_export import (
    MELODYIQ_SCOPE_RANKS_COLUMN,
    attach_melodyiq_scope_rows,
    melodyiq_scope_details,
    melodyiq_scope_export_frame,
    melodyiq_scope_key,
    melodyiq_scope_keys,
    merge_melodyiq_scope_rank_values,
)


class MelodyIQExportTests(unittest.TestCase):
    def test_scope_key_keeps_report_country_and_dates_separate(self):
        scope = melodyiq_scope_key(
            "report-1",
            creator_country="sg",
            post_created_at_min="2026-08-01",
            post_created_at_max="2026-08-21",
        )

        self.assertEqual(
            melodyiq_scope_details(scope),
            {
                "report_id": "report-1",
                "creator_country": "SG",
                "post_created_at_min": "2026-08-01",
                "post_created_at_max": "2026-08-21",
            },
        )
        self.assertNotEqual(scope, melodyiq_scope_key("report-1"))

    def test_loaded_api_export_has_no_ten_thousand_row_cap(self):
        row_count = 10001
        links = [
            f"https://www.tiktok.com/@creator/video/{7600000000000000000 + index}"
            for index in range(row_count)
        ]
        raw = pd.DataFrame(
            {
                "Link": links,
                "MelodyIQ Impact Rank": range(1, row_count + 1),
            }
        )
        normalized = pd.DataFrame(
            {
                "Platform": "TikTok",
                "Creator": "creator",
                "Link": links,
                "Track": "Example track",
                "Views": 100,
            }
        )
        scope = melodyiq_scope_key("report-large")

        tagged = attach_melodyiq_scope_rows(raw, normalized, scope)
        exported = melodyiq_scope_export_frame(tagged, scope)

        self.assertEqual(len(exported), row_count)
        self.assertEqual(exported.iloc[0]["MelodyIQ Impact Rank"], 1)
        self.assertEqual(
            exported.iloc[-1]["MelodyIQ Impact Rank"],
            row_count,
        )
        self.assertNotIn(MELODYIQ_SCOPE_RANKS_COLUMN, exported.columns)

    def test_export_includes_only_the_selected_scope(self):
        scope_one = melodyiq_scope_key("report-1")
        scope_two = melodyiq_scope_key("report-2", creator_country="MY")
        first = attach_melodyiq_scope_rows(
            pd.DataFrame(
                [{"Link": "https://www.tiktok.com/@one/video/1", "MelodyIQ Impact Rank": 1}]
            ),
            pd.DataFrame(
                [{"Link": "https://www.tiktok.com/@one/video/1", "Track": "One"}]
            ),
            scope_one,
        )
        second = attach_melodyiq_scope_rows(
            pd.DataFrame(
                [{"Link": "https://www.tiktok.com/@two/video/2", "MelodyIQ Impact Rank": 2}]
            ),
            pd.DataFrame(
                [{"Link": "https://www.tiktok.com/@two/video/2", "Track": "Two"}]
            ),
            scope_two,
        )
        combined = pd.concat([first, second], ignore_index=True)

        self.assertEqual(melodyiq_scope_keys(combined), [scope_one, scope_two])
        exported = melodyiq_scope_export_frame(combined, scope_two)
        self.assertEqual(exported["Link"].tolist(), ["https://www.tiktok.com/@two/video/2"])

    def test_scope_membership_merge_keeps_each_report_rank(self):
        scope_one = melodyiq_scope_key("report-1")
        scope_two = melodyiq_scope_key("report-2")
        merged = merge_melodyiq_scope_rank_values(
            [
                {scope_one: 1},
                {scope_two: 25},
            ]
        )
        frame = pd.DataFrame(
            [
                {
                    "Link": "https://www.tiktok.com/@one/video/1",
                    "Track": "One",
                    MELODYIQ_SCOPE_RANKS_COLUMN: merged,
                }
            ]
        )

        self.assertEqual(
            melodyiq_scope_export_frame(frame, scope_one).iloc[0][
                "MelodyIQ Impact Rank"
            ],
            1,
        )
        self.assertEqual(
            melodyiq_scope_export_frame(frame, scope_two).iloc[0][
                "MelodyIQ Impact Rank"
            ],
            25,
        )


if __name__ == "__main__":
    unittest.main()
