import ast
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from ugc_tagger.creator_profile_enrichment import creator_key


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_TREE = ast.parse(APP_PATH.read_text(encoding="utf-8"))


def safe_str(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_functions(names, namespace):
    definitions = [
        node
        for node in APP_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    module = ast.Module(body=definitions, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


class CreatorProfileRankedBackfillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {
            "Dict": Dict,
            "Tuple": Tuple,
            "creator_key": creator_key,
            "pd": pd,
            "safe_str": safe_str,
        }
        load_functions(
            {
                "_creator_profile_alias_id_v68_67",
                "_apply_creator_profile_aliases_v68_67",
                "_profile_metrics_available_keys_v68_67",
                "_profile_available_target_count_v68_67",
                "_next_creator_profile_wave_v68_67",
            },
            namespace,
        )
        cls.alias_id = staticmethod(namespace["_creator_profile_alias_id_v68_67"])
        cls.apply_aliases = staticmethod(
            namespace["_apply_creator_profile_aliases_v68_67"]
        )
        cls.available_keys = staticmethod(
            namespace["_profile_metrics_available_keys_v68_67"]
        )
        cls.next_wave = staticmethod(namespace["_next_creator_profile_wave_v68_67"])

    def ranked_targets(self, count=8):
        rows = []
        for rank in range(1, count + 1):
            creator = f"creator{rank}"
            rows.append({
                "Platform": "TikTok",
                "Creator": creator,
                "Creator Key": creator_key(creator),
                "Original Creator": creator,
                "Original Creator Key": creator_key(creator),
                "Original Target ID": self.alias_id("TikTok", creator),
                "Representative Post URL": (
                    f"https://www.tiktok.com/@{creator}/video/{1000 + rank}"
                ),
                "Rank Position": rank,
            })
        return pd.DataFrame(rows)

    @staticmethod
    def metrics(available_creators, unavailable_creators=()):
        rows = [
            {
                "Platform": "TikTok",
                "Creator Key": creator_key(creator),
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Available",
                "Profile Posts": 12,
            }
            for creator in available_creators
        ]
        rows.extend(
            {
                "Platform": "TikTok",
                "Creator Key": creator_key(creator),
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Unavailable",
                "Profile Posts": 0,
            }
            for creator in unavailable_creators
        )
        return pd.DataFrame(rows)

    def test_verified_alias_keeps_rank_identity_and_uses_current_username(self):
        targets = self.ranked_targets(1)
        aliases = {targets.iloc[0]["Original Target ID"]: "renamed.creator"}
        resolved = self.apply_aliases(targets, aliases)

        self.assertEqual(resolved.iloc[0]["Creator"], "renamed.creator")
        self.assertEqual(resolved.iloc[0]["Creator Key"], "renamed.creator")
        self.assertEqual(resolved.iloc[0]["Original Creator"], "creator1")
        self.assertEqual(resolved.iloc[0]["Rank Position"], 1)

    def test_missing_two_top_profiles_selects_exactly_next_two_ranked_creators(self):
        ranked = self.ranked_targets()
        processed = set(ranked.head(5)["Original Target ID"])
        metrics = self.metrics(
            ["creator1", "creator3", "creator5"],
            ["creator2", "creator4"],
        )

        wave, available = self.next_wave(
            ranked,
            processed,
            metrics,
            5,
            "Full 3 months",
        )

        self.assertEqual(available, 3)
        self.assertEqual(wave["Creator"].tolist(), ["creator6", "creator7"])

    def test_backfill_continues_one_at_a_time_after_one_replacement_fails(self):
        ranked = self.ranked_targets()
        processed = set(ranked.head(7)["Original Target ID"])
        metrics = self.metrics(
            ["creator1", "creator3", "creator5", "creator6"],
            ["creator2", "creator4", "creator7"],
        )

        wave, available = self.next_wave(
            ranked,
            processed,
            metrics,
            5,
            "Full 3 months",
        )

        self.assertEqual(available, 4)
        self.assertEqual(wave["Creator"].tolist(), ["creator8"])

    def test_no_recent_or_unavailable_rows_do_not_fill_requested_count(self):
        metrics = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Creator Key": "available",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Available",
                "Profile Posts": 2,
            },
            {
                "Platform": "TikTok",
                "Creator Key": "quiet",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "No recent public posts",
                "Profile Posts": 0,
            },
            {
                "Platform": "TikTok",
                "Creator Key": "blocked",
                "Profile History Mode": "Full 3 months",
                "Profile Data Status": "Unavailable",
                "Profile Posts": 0,
            },
        ])
        self.assertEqual(
            self.available_keys(metrics, "Full 3 months"),
            {("TikTok", "available")},
        )

    def test_fetch_wave_retries_verified_renamed_creator_before_paid_fallback(self):
        direct_calls = []

        def direct_metrics(_platform, creator, **_kwargs):
            direct_calls.append(creator)
            available = creator == "current_creator"
            return pd.DataFrame([{
                "Platform": "TikTok",
                "Profile Creator": creator,
                "Creator Key": creator_key(creator),
                "Profile History Mode": "Full 3 months",
                "Profile Fetched At": "2026-08-10T00:00:00+00:00",
                "Profile Data Status": "Available" if available else "Unavailable",
                "Profile Posts": 12 if available else 0,
            }])

        def direct_failed(metrics, _platform):
            return metrics.iloc[0]["Profile Data Status"] == "Unavailable"

        namespace = {
            "Callable": Callable,
            "Dict": Dict,
            "INSTAGRAM_APIFY_FALLBACK_POST_LIMIT": 20,
            "INSTAGRAM_REELS": "Instagram Reels",
            "List": List,
            "Optional": Optional,
            "TIKTOK": "TikTok",
            "Tuple": Tuple,
            "_creator_profile_alias_id_v68_67": self.alias_id,
            "_managed_api_secret_v68_43": lambda _name: "",
            "clean_api_secret": lambda value: value,
            "creator_key": creator_key,
            "creator_profile_direct_failed_v68_66": direct_failed,
            "current_tiktok_creator_handle_v68_67": (
                lambda _creator, _url: "current_creator"
            ),
            "direct_creator_profile_metrics_v68_58": direct_metrics,
            "pd": pd,
            "safe_str": safe_str,
        }
        load_functions({"_fetch_creator_profile_wave_v68_67"}, namespace)
        target = self.ranked_targets(1)
        target.loc[0, "Creator"] = "old_creator"
        target.loc[0, "Creator Key"] = "old_creator"
        target.loc[0, "Original Creator"] = "old_creator"
        target.loc[0, "Original Creator Key"] = "old_creator"
        target.loc[0, "Original Target ID"] = self.alias_id(
            "TikTok", "old_creator"
        )

        successful, failed, errors, aliases = namespace[
            "_fetch_creator_profile_wave_v68_67"
        ](
            target,
            history_mode="Full 3 months",
            history_post_limit=2_000,
        )

        self.assertEqual(direct_calls, ["old_creator", "current_creator"])
        self.assertEqual(successful.iloc[0]["Creator Key"], "current_creator")
        self.assertTrue(failed.empty)
        self.assertEqual(errors, [])
        self.assertEqual(
            aliases,
            {self.alias_id("TikTok", "old_creator"): "current_creator"},
        )


if __name__ == "__main__":
    unittest.main()
