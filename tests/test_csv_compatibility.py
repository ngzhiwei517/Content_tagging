import ast
import csv
import io
import re
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


class UploadedFile:
    def __init__(self, name: str, raw: bytes):
        self.name = name
        self._raw = raw

    def getvalue(self):
        return self._raw


class CsvCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {
            "csv": csv,
            "io": io,
            "re": re,
            "pd": pd,
            "Dict": Dict,
            "List": List,
            "Optional": Optional,
            "Tuple": Tuple,
            "MARKETS": ["PH", "MY", "KR", "SG", "VN", "TH"],
        }
        for name in [
            "safe_str",
            "clean_num",
            "is_tiktok_link",
            "extract_creator",
            "normalize_market",
            "unique_columns",
            "detect_csv_delimiter",
            "read_any_table",
            "norm_col",
            "detect_col",
            "detect_columns",
        ]:
            namespace[name] = load_function(name, namespace)
        namespace["add_performance_fields"] = lambda frame: frame.copy()
        namespace["standardize_file_rows"] = load_function("standardize_file_rows", namespace)
        cls.read_any_table = staticmethod(namespace["read_any_table"])
        cls.standardize_file_rows = staticmethod(namespace["standardize_file_rows"])

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


if __name__ == "__main__":
    unittest.main()
