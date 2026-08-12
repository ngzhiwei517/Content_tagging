import ast
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Tuple

import pandas as pd
import plotly.express as px


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
        self.assertIn('"tiktok_follower_attempted_keys_v68_65"', checkpoint_block)

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
            "Saves", "Total Engagement", "Total Views", "Average Engagement",
            "Average Views", "Average Engagements",
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
        namespace["canonical_post_date"] = lambda row: pd.to_datetime(row.get("Date"), errors="coerce")
        cls.creator_summary = staticmethod(load_function("creator_performance_summary_v68_47", namespace))
        namespace["creator_key"] = lambda value: namespace["safe_str"](value).lstrip("@").lower()
        namespace["kol_size_for_market"] = load_function("kol_size_for_market", namespace)
        cls.apply_profile_followers = staticmethod(
            load_function("apply_profile_followers_v68_64", namespace)
        )
        cls.missing_tiktok_follower_targets = staticmethod(
            load_function("missing_tiktok_follower_targets_v68_65", namespace)
        )
        namespace["FREE_FOLLOWER_LOOKUP_BATCH_SIZE_V68_68"] = 5
        cls.tiktok_follower_lookup_batches = staticmethod(
            load_function("tiktok_follower_lookup_batches_v68_68", namespace)
        )
        namespace["CREATOR_PROFILE_CACHE_TTL_SECONDS_V68_61"] = 6 * 60 * 60
        cls.pending_profile_targets = staticmethod(
            load_function("pending_creator_profile_targets_v68_61", namespace)
        )
        cls.creator_profile_direct_failed = staticmethod(
            load_function("creator_profile_direct_failed_v68_66", namespace)
        )
        cls.creative_type_chart_data = staticmethod(
            load_function("prepare_creative_type_chart_data_v68_49", namespace)
        )
        cls.creative_type_engagement_chart_data = staticmethod(
            load_function("prepare_creative_type_engagement_chart_data_v68_70", namespace)
        )
        cls.filter_summary = staticmethod(
            load_function("filter_summary_by_selected_values_v68_50", namespace)
        )
        cls.rendered_chart_figures = []
        chart_namespace = {
            "pd": pd,
            "px": px,
            "Dict": Dict,
            "Optional": __import__("typing").Optional,
            "safe_str": namespace["safe_str"],
            "clean_num": namespace["clean_num"],
            "st": SimpleNamespace(markdown=lambda *args, **kwargs: None),
            "bar_list": lambda *args, **kwargs: "",
            "chart_bar": lambda *args, **kwargs: None,
            "render_plotly_chart": lambda fig: cls.rendered_chart_figures.append(fig),
            "CREATIVE_TYPE_CHART_COLORS_V68_49": ["#6254e8", "#0ea5e9", "#10b981"],
        }
        cls.render_creative_type_bar = staticmethod(
            load_function("render_creative_type_bar_chart_v68_49", chart_namespace)
        )
        cls.render_creative_type_views = staticmethod(
            load_function("render_creative_type_views_doughnut_v68_49", chart_namespace)
        )

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

    def test_creative_type_post_chart_counts_rows_and_calculates_share(self):
        rows = pd.DataFrame([
            {"Primary Creative Type": "Dance"},
            {"Primary Creative Type": "Dance"},
            {"Primary Creative Type": "Lip Sync"},
            {"Primary Creative Type": None},
        ])
        chart = self.creative_type_chart_data(rows, "Posts")
        self.assertEqual(chart["Creative Type"].tolist(), ["Dance", "Lip Sync", "Others"])
        self.assertEqual(chart["Posts"].tolist(), [2, 1, 1])
        self.assertAlmostEqual(float(chart["Share"].sum()), 100.0)
        self.assertAlmostEqual(float(chart.loc[0, "Share"]), 50.0)

    def test_creative_type_views_chart_keeps_full_total_when_categories_collapse(self):
        rows = pd.DataFrame([
            {"Primary Creative Type": "Dance", "Views": "1,000"},
            {"Primary Creative Type": "Lip Sync", "Views": 500},
            {"Primary Creative Type": "Comedy", "Views": 250},
            {"Primary Creative Type": "POV", "Views": 100},
        ])
        chart = self.creative_type_chart_data(rows, "Views", max_categories=3)
        self.assertEqual(
            chart["Creative Type"].tolist(),
            ["Dance", "Lip Sync", "Remaining creative types"],
        )
        self.assertEqual(float(chart["Views"].sum()), 1850.0)
        self.assertAlmostEqual(float(chart["Share"].sum()), 100.0)

    def test_visual_summary_uses_interactive_post_bar_and_views_doughnut(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        self.assertIn(
            "render_creative_type_bar_chart_v68_49(mix)",
            step_six,
        )
        self.assertIn("render_creative_type_views_doughnut_v68_49(views_mix)", step_six)
        self.assertIn("prepare_creative_type_engagement_chart_data_v68_70", step_six)
        self.assertIn('prepare_creative_type_chart_data_v68_49(filtered, "Views"', step_six)
        self.assertNotIn("metric_for_chart = focus_metric", step_six)

    def test_summary_filters_allow_multiple_values_and_empty_means_all(self):
        rows = pd.DataFrame({
            "Market Display": ["SG", "MY", "TH"],
            "Primary Creative Type": ["Dance", "Lip Sync", "Dance"],
            "KOL Size Display": ["Micro", "Macro", "Nano"],
        })
        all_rows = self.filter_summary(rows, "Market Display", [])
        selected_markets = self.filter_summary(rows, "Market Display", ["SG", "TH"])
        combined = self.filter_summary(
            selected_markets,
            "Primary Creative Type",
            ["Dance"],
        )
        self.assertEqual(len(all_rows), 3)
        self.assertEqual(selected_markets["Market Display"].tolist(), ["SG", "TH"])
        self.assertEqual(combined["Market Display"].tolist(), ["SG", "TH"])

        selected_kol_sizes = self.filter_summary(
            rows,
            "KOL Size Display",
            ["Micro", "Nano"],
        )
        self.assertEqual(selected_kol_sizes["KOL Size Display"].tolist(), ["Micro", "Nano"])

    def test_summary_ui_uses_six_multiselect_filters_with_kol_size(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        filter_block = step_six.split("# Combined filters", 1)[1].split(
            "# Summary sections retain", 1
        )[0]
        self.assertEqual(filter_block.count("st.multiselect("), 6)
        self.assertNotIn("st.selectbox(", filter_block)
        self.assertEqual(filter_block.count('placeholder="All"'), 6)
        for key in [
            "summary_platform_multi_v68_50",
            "summary_source_multi_v68_50",
            "summary_market_multi_v68_50",
            "summary_track_multi_v68_50",
            "summary_type_multi_v68_50",
            "summary_kol_size_multi_v68_51",
        ]:
            self.assertIn(key, filter_block)
        self.assertIn('("KOL Size Display", kol_size_filters)', step_six)

    def test_creative_type_engagement_chart_uses_mean_rate_and_post_count(self):
        rows = pd.DataFrame({
            "Primary Creative Type": ["Dance", "Dance", "Comedy"],
            "Engagement Rate": [10.0, 20.0, 37.6],
        })
        chart = self.creative_type_engagement_chart_data(rows)
        self.assertEqual(chart["Creative Type"].tolist(), ["Comedy", "Dance"])
        self.assertEqual(chart["Posts"].tolist(), [1, 2])
        self.assertAlmostEqual(float(chart.loc[0, "Average Engagement Rate"]), 37.6)
        self.assertAlmostEqual(float(chart.loc[1, "Average Engagement Rate"]), 15.0)

    def test_creative_type_bar_hover_shows_posts_and_average_engagement_rate(self):
        self.rendered_chart_figures.clear()
        mix = pd.DataFrame({
            "Creative Type": ["Dance", "Lip Sync"],
            "Posts": [8, 2],
            "Average Engagement Rate": [14.6, 7.5],
        })
        self.render_creative_type_bar(mix)
        trace = self.rendered_chart_figures[-1].data[0]
        self.assertIn("Posts: %{customdata[0]:,.0f}", trace.hovertemplate)
        self.assertIn("Average engagement rate: %{y:.1f}%", trace.hovertemplate)
        self.assertEqual(trace.texttemplate, "%{y:.1f}%")

    def test_views_doughnut_hover_shows_view_number_and_percentage(self):
        self.rendered_chart_figures.clear()
        mix = pd.DataFrame({
            "Creative Type": ["Dance", "Lip Sync"],
            "Views": [8000, 2000],
            "Share": [80.0, 20.0],
        })
        self.render_creative_type_views(mix)
        trace = self.rendered_chart_figures[-1].data[0]
        self.assertEqual(float(trace.hole), 0.58)
        self.assertIn("Views: %{value:,.0f}", trace.hovertemplate)
        self.assertIn("Share of views: %{percent:.1%}", trace.hovertemplate)

    def test_summary_has_requested_order_and_no_median_metric(self):
        step_six = APP_SOURCE.split("# STEP 6", 1)[1]
        positions = [
            step_six.index('section_title("Market Summary"'),
            step_six.index('section_title("Track Summary"'),
            step_six.index('section_title("Sound Breakdown"'),
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
        for title in ["Platform Summary", "Market Summary", "Track Summary", "Sound Breakdown", "Source Summary"]:
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
        self.assertEqual(int(summary.loc[0, "Average Engagement"]), 60)
        self.assertAlmostEqual(float(summary.loc[0, "Average Engagement Rate"]), 15.0)

    def test_creator_campaign_performance_uses_all_posts_in_current_batch(self):
        rows = pd.DataFrame([
            {
                "Platform": "TikTok", "Market": "SG", "Creator": "Alice",
                "Date": "2026-02-01", "Views": 1_000, "Likes": 500,
            },
            {
                "Platform": "TikTok", "Market": "SG", "Creator": "Alice",
                "Date": "2026-04-01", "Views": 1_000, "Likes": 100,
            },
            {
                "Platform": "TikTok", "Market": "SG", "Creator": "Alice",
                "Date": "2026-06-30", "Views": 500, "Likes": 100,
            },
        ])
        summary, _ = self.creator_summary(rows)
        self.assertEqual(int(summary.loc[0, "Posts"]), 3)
        self.assertEqual(int(summary.loc[0, "Total Views"]), 2_500)
        self.assertEqual(int(summary.loc[0, "Total Engagement"]), 700)
        self.assertAlmostEqual(float(summary.loc[0, "Average Engagement"]), 700 / 3)
        self.assertAlmostEqual(float(summary.loc[0, "Average Engagement Rate"]), 80 / 3)

    def test_creator_section_exposes_optional_profile_enrichment_and_links(self):
        creator_section = APP_SOURCE.split("def _fetch_creator_profile_wave_v68_67", 1)[1].split(
            "def bar_list", 1
        )[0]
        self.assertIn("Fetch profile metrics", creator_section)
        self.assertIn("direct_creator_profile_metrics_v68_58", creator_section)
        self.assertIn("scrape_creator_profile_metrics", creator_section)
        self.assertIn("fallback_targets", creator_section)
        self.assertIn("direct_fallback_frames", creator_section)
        self.assertIn("target_platform in {TIKTOK, INSTAGRAM_REELS}", creator_section)
        self.assertIn("fallback_token", creator_section)
        self.assertNotIn("Use Apify for", creator_section)
        self.assertNotIn("Paid fallback profiles", creator_section)
        self.assertIn("st.number_input", creator_section)
        self.assertIn('f"Top creators (max {max_creator_count})"', creator_section)
        self.assertIn('min_value=1', creator_section)
        self.assertIn('max_value=max_creator_count', creator_section)
        self.assertIn('max_creator_count = min(100, len(target_candidates))', creator_section)
        self.assertNotIn('"Profiles to enrich"', creator_section)
        self.assertNotIn("maximum {max_post_results:,} post results", creator_section)
        self.assertNotIn("Optional enrichment checks", creator_section)
        self.assertNotIn("st.caption(", creator_section)
        self.assertNotIn('"Profile history"', creator_section)
        self.assertNotIn("PROFILE_HISTORY_OPTIONS", creator_section)
        self.assertIn("PROFILE_HISTORY_FULL", creator_section)
        self.assertIn("Profile History Mode", creator_section)
        self.assertIn(
            '["Platform", "Creator Key", "Profile History Mode"]',
            creator_section,
        )
        self.assertIn("Partial", creator_section)
        self.assertIn("creator_profile_url", creator_section)
        self.assertIn('"Creator Profile"', creator_section)
        self.assertIn("profile_history_settings", creator_section)
        self.assertIn("pending_creator_profile_targets_v68_61", creator_section)
        self.assertIn("creator_profile_direct_failed_v68_66", creator_section)
        self.assertGreaterEqual(
            creator_section.count("creator_profile_direct_failed_v68_66("), 2
        )
        self.assertIn(
            "post_limit=INSTAGRAM_APIFY_FALLBACK_POST_LIMIT",
            creator_section,
        )
        self.assertIn(
            "reconcile_creator_profile_fallback_metrics(", creator_section
        )
        self.assertIn("if fallback_targets:", creator_section)
        direct_lookup_position = creator_section.index(
            "direct_creator_profile_metrics_v68_58("
        )
        identity_recovery_position = creator_section.index(
            "current_tiktok_creator_handle_v68_67("
        )
        paid_gate_position = creator_section.index("if fallback_targets:")
        paid_call_position = creator_section.index("scrape_creator_profile_metrics(")
        self.assertLess(direct_lookup_position, identity_recovery_position)
        self.assertLess(identity_recovery_position, paid_gate_position)
        self.assertLess(direct_lookup_position, paid_gate_position)
        self.assertLess(paid_gate_position, paid_call_position)
        self.assertIn("_next_creator_profile_wave_v68_67(", creator_section)

    def test_paid_fallback_is_not_offered_for_useful_partial_direct_history(self):
        partial = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Profile Data Status": "Partial (safety limit reached)",
        }])
        unavailable = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Profile Data Status": "Unavailable",
        }])
        available = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Profile Data Status": "Available",
        }])

        self.assertFalse(
            self.creator_profile_direct_failed(partial, "Instagram Reels")
        )
        self.assertFalse(
            self.creator_profile_direct_failed(available, "Instagram Reels")
        )
        self.assertTrue(
            self.creator_profile_direct_failed(unavailable, "Instagram Reels")
        )
        self.assertTrue(
            self.creator_profile_direct_failed(pd.DataFrame(), "Instagram Reels")
        )

        missing_views = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Profile Data Status": "Available",
            "Profile Posts": 3,
            "Profile Average Views": pd.NA,
        }])
        explicit_zero_views = missing_views.copy()
        explicit_zero_views["Profile Average Views"] = 0
        self.assertTrue(
            self.creator_profile_direct_failed(missing_views, "Instagram Reels")
        )
        self.assertFalse(
            self.creator_profile_direct_failed(explicit_zero_views, "Instagram Reels")
        )
        self.assertIn(
            "returns a genuinely better metric row", APP_SOURCE
        )

    def test_profile_followers_backfill_zero_batch_values_and_kol_size(self):
        rows = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Creator": "alice",
            "Market": "SG",
            "Followers": 0,
            "KOL Size": "Unknown",
        }])
        profile_metrics = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Creator Key": "alice",
            "Current Followers": 25_000,
        }])
        enriched = self.apply_profile_followers(rows, profile_metrics)
        self.assertEqual(int(enriched.loc[0, "Followers"]), 25_000)
        self.assertEqual(enriched.loc[0, "KOL Size"], "Micro")

    def test_profile_followers_never_replace_existing_batch_value(self):
        rows = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Creator": "alice",
            "Market": "SG",
            "Followers": 12_000,
            "KOL Size": "Micro",
        }])
        profile_metrics = pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Creator Key": "alice",
            "Current Followers": 25_000,
        }])
        enriched = self.apply_profile_followers(rows, profile_metrics)
        self.assertEqual(int(enriched.loc[0, "Followers"]), 12_000)

    def test_profile_followers_match_platform_and_normalized_creator_only(self):
        rows = pd.DataFrame([
            {"Platform": "TikTok", "Creator": "@Alice", "Market": "SG", "Followers": 0, "KOL Size": "Unknown"},
            {"Platform": "Instagram Reels", "Creator": "ALICE", "Market": "SG", "Followers": 0, "KOL Size": "Unknown"},
            {"Platform": "TikTok", "Creator": "", "Market": "SG", "Followers": 0, "KOL Size": "Unknown"},
            {"Platform": "TikTok", "Creator": "bob", "Market": "SG", "Followers": "12,000", "KOL Size": "Micro"},
        ])
        profile_metrics = pd.DataFrame([
            {"Platform": "TikTok", "Creator Key": "alice", "Current Followers": 25_000},
            {"Platform": "Instagram Reels", "Creator Key": "alice", "Current Followers": 90_000},
            {"Platform": "TikTok", "Creator Key": "bob", "Current Followers": 75_000},
        ])

        enriched = self.apply_profile_followers(rows, profile_metrics)

        self.assertEqual(int(enriched.loc[0, "Followers"]), 25_000)
        self.assertEqual(int(enriched.loc[1, "Followers"]), 90_000)
        self.assertEqual(int(enriched.loc[2, "Followers"]), 0)
        self.assertEqual(enriched.loc[3, "Followers"], "12,000")
        self.assertEqual(enriched.loc[3, "KOL Size"], "Micro")

    def test_missing_tiktok_follower_targets_are_unique_and_free_lookup_is_explicit(self):
        rows = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator": "@Alice",
                "Followers": 0,
                "Link": "https://www.tiktok.com/@alice/video/123",
            },
            {"Platform": "TikTok", "Creator": "alice", "Followers": None, "Link": ""},
            {"Platform": "TikTok", "Creator": "bob", "Followers": "12,000"},
            {"Platform": "Instagram Reels", "Creator": "alice", "Followers": 0},
            {"Platform": "TikTok", "Creator": "", "Followers": 0},
        ])

        targets = self.missing_tiktok_follower_targets(rows)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets.iloc[0]["Creator Key"], "alice")
        self.assertEqual(
            targets.iloc[0]["Link"],
            "https://www.tiktok.com/@alice/video/123",
        )
        self.assertIn("Fill missing followers", APP_SOURCE)
        self.assertIn("No Apify credits are used", APP_SOURCE)
        self.assertIn("FREE_FOLLOWER_LOOKUP_BATCH_SIZE_V68_68 = 5", APP_SOURCE)
        self.assertIn("for target_batch in target_batches", APP_SOURCE)
        self.assertNotIn("pending_follower_targets.head(", APP_SOURCE)
        self.assertIn("_persist_runtime_checkpoint_v68_15()", APP_SOURCE)
        cache_section = APP_SOURCE.split(
            "def direct_tiktok_profile_followers_v68_65", 1
        )[0].rsplit("@st.cache_data", 1)[1]
        self.assertIn("max_entries=500", cache_section)

        cache_section = APP_SOURCE.split(
            "def direct_creator_profile_metrics_v68_58", 1
        )[1].split("def normalize_url_v68_15", 1)[0]
        self.assertIn("history_mode: str = DEFAULT_PROFILE_HISTORY_MODE", cache_section)
        self.assertIn("history_mode=history_mode", cache_section)

    def test_missing_follower_lookup_batches_cover_every_pending_creator(self):
        targets = pd.DataFrame([
            {"Creator Key": f"creator-{index}"}
            for index in range(8)
        ])

        batches = self.tiktok_follower_lookup_batches(targets)

        self.assertEqual([len(batch) for batch in batches], [5, 3])
        self.assertEqual(
            pd.concat(batches, ignore_index=True)["Creator Key"].tolist(),
            targets["Creator Key"].tolist(),
        )

    def test_profile_enrichment_fetches_only_additional_creators(self):
        fetched_at = pd.Timestamp.now(tz="UTC").isoformat()
        targets = pd.DataFrame([
            {"Platform": "TikTok", "Creator": f"creator{index}", "Creator Key": f"creator{index}"}
            for index in range(25)
        ])
        existing = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator Key": f"creator{index}",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Available",
                "Profile Fetched At": fetched_at,
            }
            for index in range(20)
        ])

        pending = self.pending_profile_targets(targets, existing, "Full 3 months")

        self.assertEqual(
            pending["Creator Key"].tolist(),
            [f"creator{index}" for index in range(20, 25)],
        )

    def test_profile_enrichment_retries_unavailable_creators(self):
        fetched_at = pd.Timestamp.now(tz="UTC").isoformat()
        targets = pd.DataFrame([
            {"Platform": "TikTok", "Creator": "ready", "Creator Key": "ready"},
            {"Platform": "TikTok", "Creator": "retry", "Creator Key": "retry"},
        ])
        existing = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator Key": "ready",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "No recent public posts",
                "Profile Fetched At": fetched_at,
            },
            {
                "Platform": "TikTok",
                "Creator Key": "retry",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Unavailable",
                "Profile Fetched At": fetched_at,
            },
        ])

        pending = self.pending_profile_targets(targets, existing, "Full 3 months")

        self.assertEqual(pending["Creator Key"].tolist(), ["retry"])

    def test_profile_enrichment_reuses_all_recent_completed_results(self):
        fetched_at = pd.Timestamp.now(tz="UTC").isoformat()
        targets = pd.DataFrame([
            {"Platform": "TikTok", "Creator": status, "Creator Key": status}
            for status in ("available", "none", "partial")
        ])
        existing = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator Key": "available",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Available",
                "Profile Fetched At": fetched_at,
            },
            {
                "Platform": "TikTok",
                "Creator Key": "none",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "No recent public posts",
                "Profile Fetched At": fetched_at,
            },
            {
                "Platform": "TikTok",
                "Creator Key": "partial",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Partial (safety limit reached)",
                "Profile Fetched At": fetched_at,
            },
        ])

        pending = self.pending_profile_targets(targets, existing, "Full 3 months")

        self.assertTrue(pending.empty)

    def test_profile_enrichment_refetches_stale_or_wrong_mode_results(self):
        targets = pd.DataFrame([
            {"Platform": "TikTok", "Creator": "stale", "Creator Key": "stale"},
            {"Platform": "TikTok", "Creator": "wrong", "Creator Key": "wrong"},
        ])
        existing = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator Key": "stale",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Available",
                "Profile Fetched At": (
                    pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=7)
                ).isoformat(),
            },
            {
                "Platform": "TikTok",
                "Creator Key": "wrong",
                "Profile History Mode": "Latest 20 posts",
                "Profile Data Status": "Available",
                "Profile Fetched At": pd.Timestamp.now(tz="UTC").isoformat(),
            },
        ])

        pending = self.pending_profile_targets(targets, existing, "Full 3 months")

        self.assertEqual(pending["Creator Key"].tolist(), ["stale", "wrong"])

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
        self.assertEqual(int(summary.loc[0, "Average Engagement"]), 75)
        self.assertAlmostEqual(float(summary.loc[0, "Average Engagement Rate"]), 7.5)

    def test_creator_section_does_not_render_kol_size_comparison(self):
        creator_section = APP_SOURCE.split("def render_top_creator_performance_v68_47", 1)[1].split(
            "def bar_list", 1
        )[0]
        self.assertNotIn("KOL Size Performance", creator_section)
        self.assertNotIn("by KOL Size", creator_section)

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

    def test_sortable_tables_preserve_missing_views_instead_of_zero(self):
        summary = self.prepare_summary_table(
            pd.DataFrame([
                {"Track": "Song A", "Posts": 1, "Average Views": 12.5},
                {"Track": "Song B", "Posts": 1, "Average Views": pd.NA},
            ]),
            ["Track", "Posts", "Average Views"],
        )
        self.assertEqual(summary.loc[0, "Average Views"], 12.5)
        self.assertTrue(pd.isna(summary.loc[1, "Average Views"]))
        self.assertEqual(summary["Average Views"].dtype.kind, "f")

        top_posts = self.prepare_top_posts(pd.DataFrame([{
            "Platform": "Instagram Reels",
            "Creator": "creator",
            "Views": pd.NA,
            "Total Engagement": 100,
            "Link": "https://www.instagram.com/reel/DExampleAbC1/",
        }]))
        self.assertTrue(pd.isna(top_posts.loc[0, "Views"]))
        self.assertTrue(pd.isna(top_posts.loc[0, "Engagement Rate"]))


if __name__ == "__main__":
    unittest.main()
