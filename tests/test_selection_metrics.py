import unittest

import pandas as pd

from ugc_tagger.selection_metrics import (
    merge_refreshed_metrics,
    metric_refresh_was_attempted,
    pasted_links_requiring_metrics,
    ranking_metrics_missing_count,
)


def normalize_url(value: str) -> str:
    return str(value or "").split("?", 1)[0].rstrip("/").casefold()


class SelectionMetricsTests(unittest.TestCase):
    def test_bare_links_require_metrics_before_total_engagement_ranking(self):
        frame = pd.DataFrame(
            [
                {
                    "Link": f"https://example.test/post/{index}",
                    "Views": 0,
                    "Likes": 0,
                    "Comments": 0,
                    "Shares": 0,
                    "Saves": 0,
                    "Total Engagement": 0,
                }
                for index in range(25)
            ]
        )

        self.assertEqual(
            ranking_metrics_missing_count(frame, ["Total Engagement"]),
            25,
        )

    def test_positive_file_metrics_can_be_ranked_without_refresh(self):
        frame = pd.DataFrame(
            [
                {"Link": "a", "Views": 1_000, "Total Engagement": 100},
                {"Link": "b", "Views": 2_000, "Total Engagement": 200},
            ]
        )

        self.assertEqual(
            ranking_metrics_missing_count(frame, ["Total Engagement"]),
            0,
        )
        self.assertEqual(
            ranking_metrics_missing_count(frame, ["Engagement Rate"]),
            0,
        )

    def test_attempted_unavailable_metrics_do_not_trigger_endless_refetch(self):
        frame = pd.DataFrame(
            [
                {
                    "Link": "a",
                    "Shares": pd.NA,
                    "Metrics Status": "Partial",
                    "Metrics Unavailable": "Shares, Saves",
                },
                {
                    "Link": "b",
                    "Shares": pd.NA,
                    "Metrics Status": "Not refreshed",
                    "Metrics Unavailable": "Views, Likes, Comments, Shares, Saves",
                },
            ]
        )

        self.assertEqual(ranking_metrics_missing_count(frame, ["Shares"]), 0)
        self.assertTrue(metric_refresh_was_attempted(frame))

    def test_ranking_refresh_fetches_only_missing_pasted_links(self):
        frame = pd.DataFrame(
            [
                {
                    "Link": "uploaded-ready",
                    "Source": "campaign.csv",
                    "Total Engagement": 200,
                },
                {
                    "Link": "uploaded-missing",
                    "Source": "campaign.csv",
                    "Total Engagement": 0,
                },
                {
                    "Link": "pasted-ready",
                    "Source": "Pasted links",
                    "Total Engagement": 100,
                },
                {
                    "Link": "pasted-missing",
                    "Source": " PASTED LINKS ",
                    "Total Engagement": 0,
                },
                {
                    "Link": "pasted-attempted",
                    "Source": "Pasted links",
                    "Total Engagement": 0,
                    "Metrics Status": "Partial",
                },
            ]
        )

        candidates = pasted_links_requiring_metrics(frame, ["Total Engagement"])

        self.assertEqual(candidates["Link"].tolist(), ["pasted-missing"])

    def test_refreshed_metrics_merge_by_normalized_link_and_preserve_order(self):
        batch = pd.DataFrame(
            [
                {"Link": "https://example.test/post/a?old=1", "Track": "Keep A", "Total Engagement": 0},
                {"Link": "https://example.test/post/b", "Track": "Keep B", "Total Engagement": 0},
                {"Link": "https://example.test/post/c", "Track": "Keep C", "Total Engagement": 0},
            ]
        )
        refreshed = pd.DataFrame(
            [
                {
                    "Link": "https://example.test/post/b?new=1",
                    "Views": 1_000,
                    "Likes": 90,
                    "Comments": 5,
                    "Shares": 3,
                    "Saves": 2,
                    "Total Engagement": 100,
                    "Metrics Status": "Refreshed",
                    "Metrics Unavailable": "",
                },
                {
                    "Link": "https://example.test/post/a",
                    "Views": 2_000,
                    "Likes": 180,
                    "Comments": 10,
                    "Shares": 6,
                    "Saves": 4,
                    "Total Engagement": 200,
                    "Metrics Status": "Refreshed",
                    "Metrics Unavailable": "",
                },
            ]
        )

        merged = merge_refreshed_metrics(
            batch,
            refreshed,
            normalize_url=normalize_url,
        )

        self.assertEqual(merged["Track"].tolist(), ["Keep A", "Keep B", "Keep C"])
        self.assertEqual(merged["Total Engagement"].tolist(), [200, 100, 0])
        self.assertEqual(merged.loc[0, "Metrics Status"], "Refreshed")
        self.assertTrue(pd.isna(merged.loc[2, "Metrics Status"]))
        self.assertEqual(
            merged.sort_values("Total Engagement", ascending=False).head(2)["Track"].tolist(),
            ["Keep A", "Keep B"],
        )


if __name__ == "__main__":
    unittest.main()
