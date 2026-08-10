import ast
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_TREE = ast.parse(APP_PATH.read_text(encoding="utf-8"))


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


def normalize(value):
    return str(value or "").strip().lower()


def group_key(row):
    return (str(row.get("Group") or ""),)


def removed_mask(frame):
    return frame.get(
        "Validation Status",
        pd.Series([""] * len(frame), index=frame.index),
    ).fillna("").astype(str).str.lower().eq("removed")


class TopNAvailableBackfillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {
            "Callable": Callable,
            "DEFAULT_CHUNK_SIZE": 50,
            "Dict": Dict,
            "List": List,
            "Tuple": Tuple,
            "pd": pd,
        }
        load_functions(
            {
                "_ordered_ranked_replacements_v68_58",
                "_initial_checkpoint_rows_v68_58",
                "_top_n_deficits_v68_58",
                "_unused_backfill_row_v68_58",
                "_without_unused_backfill_v68_58",
            },
            namespace,
        )
        cls.ordered = staticmethod(namespace["_ordered_ranked_replacements_v68_58"])
        cls.initial = staticmethod(namespace["_initial_checkpoint_rows_v68_58"])
        cls.deficits = staticmethod(namespace["_top_n_deficits_v68_58"])
        cls.unused_row = staticmethod(namespace["_unused_backfill_row_v68_58"])
        cls.without_unused = staticmethod(namespace["_without_unused_backfill_v68_58"])

    @staticmethod
    def rows(group, start, count):
        return [
            {
                "Group": group,
                "Link": f"https://example.com/{group}/{index}",
                "Rank": index,
            }
            for index in range(start, start + count)
        ]

    def test_replacements_preserve_rank_with_fair_group_interleaving(self):
        selected = pd.DataFrame(self.rows("A", 1, 1) + self.rows("B", 1, 1))
        ranked = pd.DataFrame(
            self.rows("A", 1, 3) + self.rows("B", 1, 3)
        )
        result = self.ordered(
            selected,
            ranked,
            group_key=group_key,
            normalize_link=normalize,
        )
        self.assertEqual(
            result[["Group", "Rank"]].values.tolist(),
            [["A", 2], ["B", 2], ["A", 3], ["B", 3]],
        )

    def test_deficit_counts_only_usable_results_in_each_group(self):
        selected = pd.DataFrame(self.rows("A", 1, 2) + self.rows("B", 1, 2))
        results = pd.DataFrame(
            [
                {"Group": "A", "Validation Status": "pass"},
                {"Group": "A", "Validation Status": "removed"},
                {"Group": "B", "Validation Status": "pass"},
                {"Group": "B", "Validation Status": "pass"},
            ]
        )
        self.assertEqual(
            self.deficits(
                selected,
                results,
                group_key=group_key,
                removed_mask=removed_mask,
            ),
            {("A",): 1, ("B",): 0},
        )

    def test_initial_checkpoint_padding_does_not_change_requested_rows(self):
        selected = pd.DataFrame(self.rows("A", 1, 30))
        replacements = pd.DataFrame(self.rows("A", 31, 30))
        initial = self.initial(
            selected,
            replacements,
            chunk_size=50,
        )
        self.assertEqual(len(initial), 50)
        self.assertEqual(initial.iloc[:30]["Link"].tolist(), selected["Link"].tolist())
        self.assertEqual(initial.iloc[30:]["Rank"].tolist(), list(range(31, 51)))

    def test_unused_checkpoint_fillers_are_never_shown_as_results(self):
        unused = self.unused_row({"Group": "A", "Link": "https://example.com/A/2"})
        visible = {"Group": "A", "Link": "https://example.com/A/1", "Tier Used": "tier1"}
        result = self.without_unused(pd.DataFrame([visible, unused]))
        self.assertEqual(result["Link"].tolist(), [visible["Link"]])
        self.assertFalse(bool(unused["Gemini Called"]))
        self.assertEqual(unused["Validation Status"], "removed")


if __name__ == "__main__":
    unittest.main()
