import ast
import unittest
from pathlib import Path
from typing import List

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def load_function(name, namespace):
    node = next(
        item
        for item in APP_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace[name]


class ReviewNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {"pd": pd, "List": List}
        cls.safe_str = staticmethod(load_function("safe_str", namespace))
        namespace["safe_str"] = cls.safe_str
        cls.queue_indices = staticmethod(
            load_function("review_queue_indices_v68_57", namespace)
        )
        cls.next_pointer = staticmethod(
            load_function("next_review_pointer_v68_57", namespace)
        )

    def test_reviewed_rows_remain_in_original_navigation_queue(self):
        tagged = pd.DataFrame(
            [
                {"Needs Review": False, "Tier Used": "tier3_human"},
                {"Needs Review": True, "Tier Used": "tier2"},
                {"Needs Review": False, "Tier Used": "tier1"},
            ],
            index=[10, 11, 12],
        )

        self.assertEqual(self.queue_indices(tagged, ["10", "11"]), [10, 11])

    def test_new_pending_rows_are_appended_to_saved_queue(self):
        tagged = pd.DataFrame(
            [
                {"Needs Review": False, "Tier Used": "tier3_human"},
                {"Needs Review": True, "Tier Used": "tier2"},
            ],
            index=[5, 7],
        )

        self.assertEqual(self.queue_indices(tagged, ["5"]), [5, 7])

    def test_save_advances_without_resetting_to_first_post(self):
        self.assertEqual(self.next_pointer(0, 3), 1)
        self.assertEqual(self.next_pointer(1, 3), 2)
        self.assertEqual(self.next_pointer(2, 3), 2)

    def test_review_queue_is_saved_with_runtime_checkpoint(self):
        checkpoint_block = APP_SOURCE.split(
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15", 1
        )[1].split(")", 1)[0]
        self.assertIn('"review_queue_indices_v68_57"', checkpoint_block)


if __name__ == "__main__":
    unittest.main()
