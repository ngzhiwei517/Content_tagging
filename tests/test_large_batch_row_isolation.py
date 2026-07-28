import ast
import logging
import unittest
from pathlib import Path
from typing import Dict, List

import pandas as pd

from ugc_tagger.final_update2_adapter import failed_analysis_review_row


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_TREE = ast.parse(APP_PATH.read_text(encoding="utf-8"))


def load_functions(names, namespace):
    wanted = set(names)
    definitions = [
        node
        for node in APP_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    module = ast.Module(body=definitions, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)


class LargeBatchRowIsolationTests(unittest.TestCase):
    @staticmethod
    def _namespace(fake_tagger):
        namespace = {
            "Dict": Dict,
            "List": List,
            "LOGGER": logging.getLogger("large-batch-test"),
            "final_update2_failed_analysis_review_row": failed_analysis_review_row,
            "final_update2_tag_candidates": fake_tagger,
            "pd": pd,
            "safe_str": lambda value: "" if value is None else str(value),
        }
        load_functions(
            [
                "_is_quota_interruption_v68_43",
                "_large_batch_must_pause_v68_43",
                "_tag_remaining_with_row_isolation_v68_43",
            ],
            namespace,
        )
        return namespace

    def test_two_hundred_rows_continue_when_one_post_fails(self):
        outputs = {}
        batch_attempts = 0
        isolated_attempts = 0
        broken_link = "https://www.instagram.com/reel/ROW_113/"

        def fake_tagger(candidates, _records, *_args, **kwargs):
            nonlocal batch_attempts, isolated_attempts
            callback = kwargs["on_result"]
            if len(candidates) > 1:
                batch_attempts += 1
                raise ValueError("post-specific synthetic failure")

            isolated_attempts += 1
            original = candidates.iloc[0].to_dict()
            if original["Link"] == broken_link:
                raise ValueError("post-specific synthetic failure")
            tagged = {
                **original,
                "Creative Type": "Dance",
                "Content Details": "Synthetic successful result",
            }
            callback(0, tagged, "tier1_cover")
            return pd.DataFrame([tagged])

        namespace = self._namespace(fake_tagger)
        run_isolated = namespace["_tag_remaining_with_row_isolation_v68_43"]

        selected = pd.DataFrame(
            [
                {
                    "Platform": "Instagram Reels",
                    "Source": "200-post simulation",
                    "Link": f"https://www.instagram.com/reel/ROW_{position:03d}/",
                    "Market": "Other",
                    "Track": "Scale track",
                    "Creator": f"creator_{position:03d}",
                }
                for position in range(200)
            ]
        )

        for chunk_start in range(0, len(selected), 50):
            chunk = selected.iloc[chunk_start:chunk_start + 50].reset_index(drop=True)
            remaining_positions = list(range(len(chunk)))
            saved_positions = set()

            def save_result(input_position, tagged_row, _tier):
                global_position = chunk_start + remaining_positions[input_position]
                outputs[global_position] = dict(tagged_row)
                saved_positions.add(remaining_positions[input_position])

            run_isolated(
                chunk,
                [],
                "test-key",
                "test-token",
                "gemini-3.1-flash-lite",
                [],
                remaining_positions,
                saved_positions,
                save_result,
                lambda *_args: None,
            )

        self.assertEqual(batch_attempts, 4)
        self.assertEqual(isolated_attempts, 200)
        self.assertEqual(len(outputs), 200)
        self.assertEqual(outputs[113]["Link"], broken_link)
        self.assertEqual(outputs[113]["Creative Type"], "Others")
        self.assertTrue(outputs[113]["Needs Review"])
        self.assertEqual(outputs[113]["Tier Used"], "runtime_manual_review")
        self.assertEqual(
            sum(row.get("Creative Type") == "Dance" for row in outputs.values()),
            199,
        )

    def test_quota_failure_pauses_without_per_post_retries(self):
        attempts = 0

        def fake_tagger(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        namespace = self._namespace(fake_tagger)
        run_isolated = namespace["_tag_remaining_with_row_isolation_v68_43"]
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Link": "https://www.tiktok.com/@creator/video/1234567890",
                }
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "RESOURCE_EXHAUSTED"):
            run_isolated(
                selected,
                [],
                "test-key",
                "test-token",
                "gemini-3.1-flash-lite",
                [],
                [0],
                set(),
                lambda *_args: None,
                lambda *_args: None,
            )
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
