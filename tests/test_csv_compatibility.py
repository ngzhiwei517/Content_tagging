import ast
import csv
import io
import re
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from instagram_reels_adapter import (
    INSTAGRAM_REELS,
    TIKTOK,
    creator_from_url as platform_creator_from_url,
    detect_platform as platform_for_url,
    is_instagram_post_url,
    is_supported_post_url,
)


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


class UploadedFile:
    def __init__(self, name: str, raw: bytes):
        self.name = name
        self._raw = raw

    def getvalue(self):
        return self._raw


class CsvCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        markets_node = next(
            item.value
            for item in APP_TREE.body
            if isinstance(item, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "MARKETS"
                for target in item.targets
            )
        )
        cls.markets = ast.literal_eval(markets_node)
        namespace = {
            "csv": csv,
            "io": io,
            "re": re,
            "pd": pd,
            "Dict": Dict,
            "List": List,
            "Optional": Optional,
            "Tuple": Tuple,
            "MARKETS": cls.markets,
            "TIKTOK": TIKTOK,
            "INSTAGRAM_REELS": INSTAGRAM_REELS,
            "platform_for_url": platform_for_url,
            "platform_creator_from_url": platform_creator_from_url,
            "is_instagram_post_url": is_instagram_post_url,
            "is_supported_post_url": is_supported_post_url,
        }
        for name in [
            "safe_str",
            "clean_num",
            "is_tiktok_link",
            "is_instagram_link",
            "post_platform",
            "is_supported_link",
            "extract_creator",
            "display_market",
            "kol_size_for_market",
            "normalize_market",
            "unique_columns",
            "detect_csv_delimiter",
            "read_any_table",
            "norm_col",
            "detect_col",
            "detect_columns",
            "coalesce_duplicate_batch_rows",
        ]:
            namespace[name] = load_function(name, namespace)
        namespace["add_performance_fields"] = lambda frame: frame.copy()
        namespace["standardize_file_rows"] = load_function("standardize_file_rows", namespace)
        cls.read_any_table = staticmethod(namespace["read_any_table"])
        cls.standardize_file_rows = staticmethod(namespace["standardize_file_rows"])
        cls.kol_size_for_market = staticmethod(namespace["kol_size_for_market"])
        cls.display_market = staticmethod(namespace["display_market"])
        cls.normalize_market = staticmethod(namespace["normalize_market"])
        cls.coalesce_duplicate_batch_rows = staticmethod(namespace["coalesce_duplicate_batch_rows"])

    def parse(self, text: str, *, encoding: str = "utf-8", name: str = "test.csv"):
        raw = text.encode(encoding)
        frame = self.read_any_table(UploadedFile(name, raw))
        return self.standardize_file_rows(frame, name)

    def test_utf8_bom_and_generic_headers(self):
        text = (
            "TikTok Link,Country,Song Name,Username,View Count,Like Count,Comment Count,Share Count,Save Count\n"
            'https://www.tiktok.com/@alpha/video/7600000000000000001,Malaysia,Track A,alpha,"1,234",200,10,5,3\n'
        )
        rows, columns = self.parse(text, encoding="utf-8-sig", name="generic.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(columns["link"], "TikTok Link")
        self.assertEqual(rows.loc[0, "Market"], "MY")
        self.assertEqual(rows.loc[0, "Track"], "Track A")
        self.assertEqual(rows.loc[0, "Views"], 1234)

    def test_instagram_reel_file_uses_the_same_canonical_schema(self):
        text = (
            "Instagram Reel URL,Market,Track Name,View Count,Like Count\n"
            "https://www.instagram.com/reel/DExampleAbC1/?utm_source=test,SG,Track IG,5000,250\n"
        )
        rows, columns = self.parse(text, name="instagram.csv")
        self.assertEqual(columns["link"], "Instagram Reel URL")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.loc[0, "Platform"], INSTAGRAM_REELS)
        self.assertEqual(rows.loc[0, "Market"], "SG")
        self.assertEqual(rows.loc[0, "Track"], "Track IG")

    def test_indonesia_market_name_normalizes_to_id(self):
        self.assertIn("ID", self.markets)
        self.assertIn(
            'MARKET_OPTIONS = ["Other / no market"] + MARKETS',
            APP_SOURCE,
        )
        text = (
            "TikTok Link,Market,Track Name,Followers\n"
            "https://www.tiktok.com/@indo/video/7600000000000000010,Indonesia,Track ID,25000\n"
        )
        rows, _ = self.parse(text, name="indonesia.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.loc[0, "Market"], "ID")
        self.assertEqual(rows.loc[0, "Track"], "Track ID")

    def test_explicit_market_column_wins_over_conflicting_country(self):
        text = (
            "TikTok Link,Country,Market,Track Name\n"
            "https://www.tiktok.com/@indo/video/7600000000000000097,KR,ID,Track ID\n"
        )
        rows, columns = self.parse(text, name="market_precedence.csv")
        self.assertEqual(columns["market"], "Market")
        self.assertEqual(rows.loc[0, "Market"], "ID")

    def test_all_indonesia_aliases_normalize_to_id(self):
        for alias in ["Indonesia", "Indonesian", "IDN"]:
            with self.subTest(alias=alias):
                self.assertEqual(self.normalize_market(alias), "ID")

    def test_other_and_unsupported_market_values_remain_blank(self):
        for value in ["Other / no market", "Unknown", "Atlantis", "XX"]:
            with self.subTest(value=value):
                self.assertEqual(self.normalize_market(value), "")

    def test_indonesia_uses_its_market_specific_kol_thresholds(self):
        self.assertEqual(self.display_market("Indonesia"), "ID")
        self.assertEqual(self.display_market("IDN"), "ID")
        boundaries = [
            (0, "Unknown"),
            (1000, "Buzzer"),
            (1001, "Nano"),
            (10000, "Nano"),
            (10001, "Micro"),
            (50000, "Micro"),
            (50001, "Medium"),
            (200000, "Medium"),
            (200001, "Macro"),
            (1000000, "Macro"),
            (1000001, "Mega"),
        ]
        for followers, expected in boundaries:
            with self.subTest(followers=followers):
                self.assertEqual(
                    self.kol_size_for_market(followers, "Indonesia"),
                    expected,
                )

    def test_semicolon_creator_export_headers(self):
        text = (
            "Post Link;Market Code;Track Title;Creator Username;Followers Count;Video Views;Video Likes;Video Comments;Video Shares;Video Saves\n"
            "https://www.tiktok.com/@bravo/video/7600000000000000002;PH;Track B;bravo;25000;9000;800;30;20;15\n"
        )
        rows, columns = self.parse(text, name="creator_export.csv")
        self.assertEqual(columns["link"], "Post Link")
        self.assertEqual(rows.loc[0, "Creator"], "bravo")
        self.assertEqual(rows.loc[0, "Followers"], 25000)
        self.assertEqual(rows.loc[0, "Total Engagement"], 865)

    def test_tab_delimited_apify_headers(self):
        text = (
            "webVideoUrl\tregion\tmusicName\tauthorMeta.fansCount\tplayCount\tdiggCount\tcommentCount\tshareCount\tcollectCount\n"
            "https://www.tiktok.com/@charlie/video/7600000000000000003\tSG\tTrack C\t3200\t50000\t4000\t120\t80\t40\n"
        )
        rows, columns = self.parse(text, name="apify_export.csv")
        self.assertEqual(columns["link"], "webVideoUrl")
        self.assertEqual(rows.loc[0, "Market"], "SG")
        self.assertEqual(rows.loc[0, "Track"], "Track C")
        self.assertEqual(rows.loc[0, "Saves"], 40)

    def test_pipe_delimited_minimal_permalink(self):
        text = (
            "Permalink|Notes\n"
            "https://www.tiktok.com/@delta/video/7600000000000000004|link-only input\n"
        )
        rows, columns = self.parse(text, name="minimal.csv")
        self.assertEqual(columns["link"], "Permalink")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.loc[0, "Creator"], "delta")
        self.assertEqual(rows.loc[0, "Market"], "")

    def test_utf16_semicolon_file(self):
        text = (
            "Video Link;Country Code;Song Title;Post Views\n"
            "https://www.tiktok.com/@echo/video/7600000000000000005;Vietnam;Track E;7654\n"
        )
        rows, columns = self.parse(text, encoding="utf-16", name="utf16.csv")
        self.assertEqual(columns["link"], "Video Link")
        self.assertEqual(rows.loc[0, "Market"], "VN")
        self.assertEqual(rows.loc[0, "Views"], 7654)

    def test_file_without_tiktok_link_column_is_rejected(self):
        rows, columns = self.parse("Campaign,Views\nExample,100\n", name="invalid.csv")
        self.assertIsNone(columns["link"])
        self.assertTrue(rows.empty)

    def test_campaign_song_used_header_populates_track(self):
        text = (
            "TikTok Link,Campaign Song Used,Market\n"
            "https://www.tiktok.com/@audio/video/7600000000000000011,Artist - Track Name,VN\n"
        )
        rows, columns = self.parse(text, name="campaign_song.csv")
        self.assertEqual(columns["track"], "Campaign Song Used")
        self.assertEqual(rows.loc[0, "Track"], "Artist - Track Name")

    def test_optional_campaign_artist_column_is_preserved(self):
        text = (
            "TikTok Link,Track Name,Artist Name,Market\n"
            "https://www.tiktok.com/@audio/video/7600000000000000099,Hit the Wall,Gracie Abrams,MY\n"
        )
        rows, columns = self.parse(text, name="artist_track.csv")
        self.assertEqual(columns["artist"], "Artist Name")
        self.assertEqual(rows.loc[0, "Track"], "Hit the Wall")
        self.assertEqual(rows.loc[0, "Campaign Artist"], "Gracie Abrams")

    def test_duplicate_pasted_link_backfills_track_without_changing_first_source_order(self):
        link = "https://www.tiktok.com/@audio/video/7600000000000000012"
        combined = pd.DataFrame([
            {"Source": "upload.csv", "Input Type": "CSV/XLSX", "Link": link, "Track": "", "Market": "", "Views": 0},
            {"Source": "Pasted links", "Input Type": "Pasted", "Link": link, "Track": "Example Song", "Market": "VN", "Views": 125},
        ])
        combined["_link_key"] = combined["Link"]
        merged = self.coalesce_duplicate_batch_rows(combined)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.loc[0, "Source"], "upload.csv")
        self.assertEqual(merged.loc[0, "Track"], "Example Song")
        self.assertEqual(merged.loc[0, "Market"], "VN")
        self.assertEqual(merged.loc[0, "Views"], 125)

    def test_duplicate_row_backfills_canonical_indonesia_market(self):
        link = "https://www.tiktok.com/@audio/video/7600000000000000098"
        combined = pd.DataFrame([
            {
                "Source": "upload.csv",
                "Input Type": "CSV/XLSX",
                "Link": link,
                "Track": "Example Song",
                "Market": "Other / no market",
                "Views": 0,
            },
            {
                "Source": "Pasted links",
                "Input Type": "Pasted",
                "Link": link,
                "Track": "",
                "Market": "Indonesian",
                "Views": 125,
            },
        ])
        combined["_link_key"] = combined["Link"]
        merged = self.coalesce_duplicate_batch_rows(combined)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.loc[0, "Source"], "upload.csv")
        self.assertEqual(merged.loc[0, "Market"], "ID")
        self.assertEqual(merged.loc[0, "Views"], 125)


if __name__ == "__main__":
    unittest.main()
