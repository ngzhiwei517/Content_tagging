import ast
import copy
import logging
import shutil
import tempfile
import time
import unittest
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

import ugc_tagger.final_update2_adapter as adapter
from ugc_tagger.batch_checkpoint import BatchCheckpointStore


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_TREE = ast.parse(APP_PATH.read_text(encoding="utf-8"))


class _State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class _Element:
    def write(self, *_args, **_kwargs):
        return None

    def update(self, *_args, **_kwargs):
        return None

    def progress(self, *_args, **_kwargs):
        return None


class _Streamlit:
    def __init__(self):
        self.session_state = _State(runtime_run_id_v68_15="a" * 32)
        self.errors = []

    def status(self, *_args, **_kwargs):
        return _Element()

    def progress(self, *_args, **_kwargs):
        return _Element()

    def empty(self):
        return _Element()

    def error(self, message):
        self.errors.append(str(message))

    def warning(self, message):
        self.errors.append(str(message))


class _MemoryCheckpointObjects:
    def __init__(self):
        self.objects = {}

    def save(self, key, payload):
        self.objects[key] = copy.deepcopy(payload)

    def load(self, key):
        return copy.deepcopy(self.objects.get(key))

    def list_prefix(self, prefix):
        return {
            key: copy.deepcopy(payload)
            for key, payload in self.objects.items()
            if key.startswith(prefix)
        }

    def delete(self, key):
        self.objects.pop(key, None)

    def delete_prefix(self, prefix):
        for key in [key for key in self.objects if key.startswith(prefix)]:
            self.objects.pop(key, None)


class _FailPartialCheckpointObjects(_MemoryCheckpointObjects):
    def save(self, key, payload):
        if "/partial_" in key and "/row_" in key:
            raise RuntimeError("synthetic remote checkpoint failure")
        super().save(key, payload)


def _load_runner(namespace):
    namespace.setdefault(
        "_checkpoint_candidates_v68_58",
        lambda selected, _batch: (selected.reset_index(drop=True), pd.DataFrame()),
    )
    namespace.setdefault(
        "_checkpoint_execution_rows_v68_58",
        lambda initial, _replacements, _manifest: initial.reset_index(drop=True),
    )
    namespace.setdefault(
        "_extend_top_n_checkpoint_v68_58",
        lambda _store, manifest, _selected, _replacements, _rows: (
            manifest,
            False,
            {},
        ),
    )
    namespace.setdefault(
        "_without_unused_backfill_v68_58",
        lambda frame: frame,
    )
    namespace.setdefault(
        "_top_n_deficits_v68_58",
        lambda _selected, _results, **_kwargs: {},
    )
    namespace.setdefault(
        "_unused_backfill_row_v68_58",
        lambda row: row.to_dict() | {
            "Review Action": "REMOVE",
            "Validation Status": "removed",
        },
    )
    namespace.setdefault(
        "_selection_group_key_v56",
        lambda _row: ("All selected posts",),
    )
    namespace.setdefault(
        "_removed_mask_v56",
        lambda frame: pd.Series([False] * len(frame), index=frame.index),
    )
    namespace.setdefault(
        "final_update2_normalize_url",
        lambda value: str(value or "").strip(),
    )
    definition = next(
        node
        for node in APP_TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_run_checkpointed_tag_every_link_v68_43"
    )
    module = ast.Module(body=[definition], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace["_run_checkpointed_tag_every_link_v68_43"]


class LargeBatchScrapeWindowTests(unittest.TestCase):
    def test_top_fifty_backfills_unavailable_rows_without_tagging_surplus(self):
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "Top 50 simulation",
                    "Link": f"https://www.tiktok.com/@creator/video/{950000 + index}",
                    "Market": "SG",
                    "Track": "Ranked track",
                    "Creator": f"creator_{index}",
                }
                for index in range(50)
            ]
        )
        replacements = pd.DataFrame(
            [
                selected.iloc[0].to_dict()
                | {
                    "Link": f"https://www.tiktok.com/@replacement/video/{959000 + index}",
                    "Creator": f"replacement_{index}",
                }
                for index in range(10)
            ]
        )
        unavailable_links = set(selected.iloc[:5]["Link"])
        scrape_sizes = []
        tag_calls = []
        fake_st = _Streamlit()

        def normalize(value):
            return str(value or "").strip()

        def removed_mask(frame):
            return frame.get(
                "Validation Status",
                pd.Series([""] * len(frame), index=frame.index),
            ).fillna("").astype(str).str.lower().eq("removed")

        def deficits(_selected, results, **_kwargs):
            usable = results.loc[~removed_mask(results)] if not results.empty else results
            return {("All selected posts",): max(0, 50 - len(usable))}

        def execution_rows(initial, pool, manifest):
            rows = initial.copy()
            requested = list(manifest.get("backfill_links", []))
            if requested:
                rows = pd.concat(
                    [rows, pool[pool["Link"].isin(requested)]],
                    ignore_index=True,
                )
            return rows.reset_index(drop=True)

        def extend(store, manifest, _selected, pool, rows):
            missing = deficits(_selected, store.load_completed_results(manifest))
            if not any(missing.values()):
                return manifest, False, missing
            attempted = set(rows["Link"])
            wave = pool[~pool["Link"].isin(attempted)].head(50)
            if wave.empty:
                return manifest, False, missing
            return (
                store.extend_with_backfill_links(manifest, wave["Link"].tolist()),
                True,
                missing,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def scrape(links, _token, **_kwargs):
                scrape_sizes.append(len(links))
                return [
                    {"submittedVideoUrl": link, "webVideoUrl": link}
                    for link in links
                ]

            def tag_rows(
                remaining,
                _records,
                _gemini_key,
                _apify_token,
                _model,
                _logs,
                _remaining_positions,
                _saved_positions,
                on_result,
                on_progress,
            ):
                for position, (_, row) in enumerate(remaining.iterrows()):
                    link = row["Link"]
                    tag_calls.append(link)
                    removed = link in unavailable_links
                    on_result(
                        position,
                        row.to_dict()
                        | {
                            "Creative Type": "Others",
                            "Review Action": "REMOVE" if removed else "",
                            "Validation Status": "removed" if removed else "pass",
                        },
                        "auto_removed_unavailable" if removed else "tier1_cover",
                    )
                    on_progress(position + 1, len(remaining), "tier1_cover")

            namespace = {
                "BatchCheckpointStore": BatchCheckpointStore,
                "Dict": Dict,
                "List": List,
                "LOGGER": logging.getLogger("top-fifty-backfill-test"),
                "MAX_APIFY_POSTS_PER_EXECUTION_V68_54": 25,
                "MAX_LIVE_POSTS_PER_EXECUTION_V68_52": 5,
                "Optional": Optional,
                "REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52": 5,
                "_attach_comparison_metadata_v68_43": lambda frame, _manifest: frame,
                "_checkpoint_candidates_v68_58": lambda frame, _batch: (
                    frame.reset_index(drop=True),
                    replacements,
                ),
                "_checkpoint_execution_rows_v68_58": execution_rows,
                "_extend_top_n_checkpoint_v68_58": extend,
                "_final_update2_adapter": adapter,
                "_is_quota_interruption_v68_43": lambda _exc: False,
                "_large_batch_error_code_v68_43": lambda _exc: "TEST_ERROR",
                "_large_batch_store_v68_43": lambda: BatchCheckpointStore(root),
                "_persist_runtime_checkpoint_v68_15": lambda: None,
                "_removed_mask_v56": removed_mask,
                "_render_run_log_v45": lambda *_args: None,
                "_route_sensitive_for_selection_v56": lambda frame, _mode: (frame, 0),
                "_selection_group_key_v56": lambda _row: ("All selected posts",),
                "_tag_remaining_with_row_isolation_v68_43": tag_rows,
                "_top_n_deficits_v68_58": deficits,
                "_unused_backfill_row_v68_58": lambda row: row.to_dict()
                | {
                    "Review Action": "REMOVE",
                    "Validation Status": "removed",
                    "Tier Used": "backfill_not_needed",
                },
                "_valid_runtime_id_v68_15": lambda value: value,
                "_without_unused_backfill_v68_58": lambda frame: frame.loc[
                    ~frame.get(
                        "Tier Used",
                        pd.Series([""] * len(frame), index=frame.index),
                    ).fillna("").astype(str).eq("backfill_not_needed")
                ].reset_index(drop=True),
                "datetime": datetime,
                "final_update2_normalize_url": normalize,
                "final_update2_review_cache": adapter.review_cache,
                "final_update2_scrape_links": scrape,
                "gemini_model_slug": lambda _model: "test-model",
                "is_supported_link": lambda _link: True,
                "pd": pd,
                "platform_for_url": adapter.detect_platform,
                "safe_str": lambda value: "" if value is None else str(value),
                "st": fake_st,
                "time": time,
                "timezone": timezone,
                "uuid": uuid,
            }
            runner = _load_runner(namespace)
            result = None
            for _ in range(40):
                result = runner(selected, "gemini-key", "apify-token", "test-model")
                if result is not None:
                    break

        self.assertIsInstance(result, pd.DataFrame)
        usable = result.loc[~removed_mask(result)]
        self.assertEqual(len(usable), 50)
        self.assertEqual(len(tag_calls), 55)
        self.assertEqual(tag_calls[-5:], replacements.iloc[:5]["Link"].tolist())
        self.assertEqual(scrape_sizes, [25, 25, 5])
        self.assertFalse(fake_st.errors)

    def test_two_hundred_fifty_posts_never_reach_apify_in_one_request(self):
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "250-post simulation",
                    "Link": f"https://www.tiktok.com/@creator/video/{980000 + index}",
                    "Market": "SG",
                    "Track": "Scale track",
                    "Creator": f"creator_{index}",
                }
                for index in range(250)
            ]
        )
        scrape_sizes = []
        fake_st = _Streamlit()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def scrape(links, _token, **_kwargs):
                scrape_sizes.append(len(links))
                return [
                    {"submittedVideoUrl": link, "webVideoUrl": link}
                    for link in links
                ]

            def tag_rows(
                remaining,
                _records,
                _gemini_key,
                _apify_token,
                _model,
                _logs,
                _remaining_positions,
                _saved_positions,
                on_result,
                on_progress,
            ):
                for position, (_, row) in enumerate(remaining.iterrows()):
                    tagged = row.to_dict() | {
                        "Creative Type": "Others",
                        "Content Details": "Synthetic result",
                    }
                    on_result(position, tagged, "tier1_cover")
                    on_progress(position + 1, len(remaining), "tier1_cover")

            namespace = {
                "BatchCheckpointStore": BatchCheckpointStore,
                "Dict": Dict,
                "List": List,
                "LOGGER": logging.getLogger("250-post-scrape-window-test"),
                "MAX_APIFY_POSTS_PER_EXECUTION_V68_54": 25,
                "MAX_LIVE_POSTS_PER_EXECUTION_V68_52": 5,
                "Optional": Optional,
                "REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52": 5,
                "_attach_comparison_metadata_v68_43": lambda frame, _manifest: frame,
                "_final_update2_adapter": adapter,
                "_is_quota_interruption_v68_43": lambda _exc: False,
                "_large_batch_error_code_v68_43": lambda _exc: "TEST_ERROR",
                "_large_batch_store_v68_43": lambda: BatchCheckpointStore(root),
                "_persist_runtime_checkpoint_v68_15": lambda: None,
                "_render_run_log_v45": lambda *_args: None,
                "_route_sensitive_for_selection_v56": lambda frame, _mode: (frame, 0),
                "_tag_remaining_with_row_isolation_v68_43": tag_rows,
                "_valid_runtime_id_v68_15": lambda value: value,
                "datetime": datetime,
                "final_update2_review_cache": adapter.review_cache,
                "final_update2_scrape_links": scrape,
                "gemini_model_slug": lambda _model: "test-model",
                "is_supported_link": lambda _link: True,
                "pd": pd,
                "platform_for_url": adapter.detect_platform,
                "safe_str": lambda value: "" if value is None else str(value),
                "st": fake_st,
                "time": time,
                "timezone": timezone,
                "uuid": uuid,
            }
            runner = _load_runner(namespace)

            result = None
            execution_count = 0
            while result is None and execution_count < 100:
                result = runner(selected, "gemini-key", "apify-token", "test-model")
                execution_count += 1

        self.assertFalse(fake_st.errors)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 250)
        self.assertEqual(result["Link"].tolist(), selected["Link"].tolist())
        self.assertEqual(scrape_sizes, [25] * 10)
        self.assertLess(execution_count, 100)

    def test_abrupt_restart_after_three_tags_does_not_repeat_paid_work(self):
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "abrupt-restart simulation",
                    "Link": f"https://www.tiktok.com/@creator/video/{970000 + index}",
                    "Market": "SG",
                    "Track": "Restart track",
                    "Creator": f"creator_{index}",
                }
                for index in range(50)
            ]
        )
        scrape_sizes = []
        tag_calls = Counter()
        remote = _MemoryCheckpointObjects()
        crashed = False

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"

            def scrape(links, _token, **_kwargs):
                scrape_sizes.append(len(links))
                return [
                    {"submittedVideoUrl": link, "webVideoUrl": link}
                    for link in links
                ]

            def tag_rows(
                remaining,
                _records,
                _gemini_key,
                _apify_token,
                _model,
                _logs,
                _remaining_positions,
                _saved_positions,
                on_result,
                on_progress,
            ):
                nonlocal crashed
                for position, (_, row) in enumerate(remaining.iterrows()):
                    link = row["Link"]
                    tag_calls[link] += 1
                    tagged = row.to_dict() | {
                        "Creative Type": "Others",
                        "Content Details": "Synthetic result",
                    }
                    on_result(position, tagged, "tier1_cover")
                    on_progress(position + 1, len(remaining), "tier1_cover")
                    if not crashed and position == 2:
                        crashed = True
                        raise SystemExit("simulated process replacement")

            fake_st = _Streamlit()
            namespace = {
                "BatchCheckpointStore": BatchCheckpointStore,
                "Dict": Dict,
                "List": List,
                "LOGGER": logging.getLogger("abrupt-restart-test"),
                "MAX_APIFY_POSTS_PER_EXECUTION_V68_54": 25,
                "MAX_LIVE_POSTS_PER_EXECUTION_V68_52": 5,
                "Optional": Optional,
                "REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52": 5,
                "_attach_comparison_metadata_v68_43": lambda frame, _manifest: frame,
                "_final_update2_adapter": adapter,
                "_is_quota_interruption_v68_43": lambda _exc: False,
                "_large_batch_error_code_v68_43": lambda _exc: "TEST_ERROR",
                "_large_batch_store_v68_43": lambda: BatchCheckpointStore(
                    root,
                    persistent_store=remote,
                ),
                "_persist_runtime_checkpoint_v68_15": lambda: None,
                "_render_run_log_v45": lambda *_args: None,
                "_route_sensitive_for_selection_v56": lambda frame, _mode: (frame, 0),
                "_tag_remaining_with_row_isolation_v68_43": tag_rows,
                "_valid_runtime_id_v68_15": lambda value: value,
                "datetime": datetime,
                "final_update2_review_cache": adapter.review_cache,
                "final_update2_scrape_links": scrape,
                "gemini_model_slug": lambda _model: "test-model",
                "is_supported_link": lambda _link: True,
                "pd": pd,
                "platform_for_url": adapter.detect_platform,
                "safe_str": lambda value: "" if value is None else str(value),
                "st": fake_st,
                "time": time,
                "timezone": timezone,
                "uuid": uuid,
            }
            runner = _load_runner(namespace)

            self.assertIsNone(
                runner(selected, "gemini-key", "apify-token", "test-model")
            )
            with self.assertRaisesRegex(SystemExit, "process replacement"):
                runner(selected, "gemini-key", "apify-token", "test-model")

            # Simulate a new Streamlit container: local files and Session State
            # are gone, while Supabase/Postgres checkpoint objects remain.
            shutil.rmtree(root)
            namespace["st"] = _Streamlit()

            result = None
            execution_count = 0
            while result is None and execution_count < 30:
                result = runner(
                    selected,
                    "replacement-gemini-key",
                    "apify-token",
                    "test-model",
                )
                execution_count += 1

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 50)
        self.assertEqual(scrape_sizes, [25, 25])
        self.assertEqual(len(tag_calls), 50)
        self.assertTrue(all(count == 1 for count in tag_calls.values()))
        persisted = str(remote.objects)
        self.assertNotIn("gemini-key", persisted)
        self.assertNotIn("apify-token", persisted)

    def test_sub_25_restart_does_not_repeat_paid_work(self):
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "small-restart simulation",
                    "Link": f"https://www.tiktok.com/@creator/video/{980000 + index}",
                    "Market": "SG",
                    "Track": "Small restart track",
                    "Creator": f"creator_{index}",
                }
                for index in range(12)
            ]
        )
        scrape_sizes = []
        tag_calls = Counter()
        remote = _MemoryCheckpointObjects()
        crashed = False

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"

            def scrape(links, _token, **_kwargs):
                scrape_sizes.append(len(links))
                return [
                    {"submittedVideoUrl": link, "webVideoUrl": link}
                    for link in links
                ]

            def tag_rows(
                remaining,
                _records,
                _gemini_key,
                _apify_token,
                _model,
                _logs,
                _remaining_positions,
                _saved_positions,
                on_result,
                on_progress,
            ):
                nonlocal crashed
                for position, (_, row) in enumerate(remaining.iterrows()):
                    link = row["Link"]
                    tag_calls[link] += 1
                    tagged = row.to_dict() | {
                        "Creative Type": "Others",
                        "Content Details": "Synthetic result",
                    }
                    on_result(position, tagged, "tier1_cover")
                    on_progress(position + 1, len(remaining), "tier1_cover")
                    if not crashed and position == 2:
                        crashed = True
                        raise SystemExit("simulated small process replacement")

            fake_st = _Streamlit()
            namespace = {
                "BatchCheckpointStore": BatchCheckpointStore,
                "Dict": Dict,
                "List": List,
                "LOGGER": logging.getLogger("small-restart-test"),
                "MAX_APIFY_POSTS_PER_EXECUTION_V68_54": 25,
                "MAX_LIVE_POSTS_PER_EXECUTION_V68_52": 5,
                "Optional": Optional,
                "REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52": 5,
                "_attach_comparison_metadata_v68_43": lambda frame, _manifest: frame,
                "_final_update2_adapter": adapter,
                "_is_quota_interruption_v68_43": lambda _exc: False,
                "_large_batch_error_code_v68_43": lambda _exc: "TEST_ERROR",
                "_large_batch_store_v68_43": lambda: BatchCheckpointStore(
                    root,
                    persistent_store=remote,
                ),
                "_persist_runtime_checkpoint_v68_15": lambda: None,
                "_render_run_log_v45": lambda *_args: None,
                "_route_sensitive_for_selection_v56": lambda frame, _mode: (frame, 0),
                "_tag_remaining_with_row_isolation_v68_43": tag_rows,
                "_valid_runtime_id_v68_15": lambda value: value,
                "datetime": datetime,
                "final_update2_review_cache": adapter.review_cache,
                "final_update2_scrape_links": scrape,
                "gemini_model_slug": lambda _model: "test-model",
                "is_supported_link": lambda _link: True,
                "pd": pd,
                "platform_for_url": adapter.detect_platform,
                "safe_str": lambda value: "" if value is None else str(value),
                "st": fake_st,
                "time": time,
                "timezone": timezone,
                "uuid": uuid,
            }
            runner = _load_runner(namespace)

            with self.assertRaisesRegex(SystemExit, "small process replacement"):
                runner(selected, "gemini-key", "apify-token", "test-model")

            # A new container has no local files or Session State, but the
            # per-row remote checkpoints must prevent repeated Gemini calls.
            shutil.rmtree(root)
            namespace["st"] = _Streamlit()

            result = None
            execution_count = 0
            while result is None and execution_count < 20:
                result = runner(
                    selected,
                    "replacement-gemini-key",
                    "apify-token",
                    "test-model",
                )
                execution_count += 1

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 12)
        self.assertEqual(scrape_sizes, [12])
        self.assertEqual(len(tag_calls), 12)
        self.assertTrue(all(count == 1 for count in tag_calls.values()))

    def test_remote_checkpoint_failure_pauses_before_second_paid_tag(self):
        selected = pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "storage-failure simulation",
                    "Link": f"https://www.tiktok.com/@creator/video/{960000 + index}",
                    "Market": "SG",
                    "Track": "Storage track",
                    "Creator": f"creator_{index}",
                }
                for index in range(50)
            ]
        )
        remote = _FailPartialCheckpointObjects()
        tag_calls = []
        fake_st = _Streamlit()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"

            def scrape(links, _token, **_kwargs):
                return [
                    {"submittedVideoUrl": link, "webVideoUrl": link}
                    for link in links
                ]

            def tag_rows(
                remaining,
                _records,
                _gemini_key,
                _apify_token,
                _model,
                _logs,
                _remaining_positions,
                _saved_positions,
                on_result,
                on_progress,
            ):
                for position, (_, row) in enumerate(remaining.iterrows()):
                    tag_calls.append(row["Link"])
                    on_result(
                        position,
                        row.to_dict() | {"Creative Type": "Others"},
                        "tier1_cover",
                    )
                    on_progress(position + 1, len(remaining), "tier1_cover")

            namespace = {
                "BatchCheckpointStore": BatchCheckpointStore,
                "Dict": Dict,
                "List": List,
                "LOGGER": logging.getLogger("storage-failure-test"),
                "MAX_APIFY_POSTS_PER_EXECUTION_V68_54": 25,
                "MAX_LIVE_POSTS_PER_EXECUTION_V68_52": 5,
                "Optional": Optional,
                "REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52": 5,
                "_attach_comparison_metadata_v68_43": lambda frame, _manifest: frame,
                "_final_update2_adapter": adapter,
                "_is_quota_interruption_v68_43": lambda _exc: False,
                "_large_batch_error_code_v68_43": (
                    lambda exc: (
                        "CHECKPOINT_STORAGE"
                        if "REMOTE_CHECKPOINT_WRITE_FAILED" in str(exc)
                        else "TEST_ERROR"
                    )
                ),
                "_large_batch_store_v68_43": lambda: BatchCheckpointStore(
                    root,
                    persistent_store=remote,
                ),
                "_persist_runtime_checkpoint_v68_15": lambda: None,
                "_render_run_log_v45": lambda *_args: None,
                "_route_sensitive_for_selection_v56": lambda frame, _mode: (frame, 0),
                "_tag_remaining_with_row_isolation_v68_43": tag_rows,
                "_valid_runtime_id_v68_15": lambda value: value,
                "datetime": datetime,
                "final_update2_review_cache": adapter.review_cache,
                "final_update2_scrape_links": scrape,
                "gemini_model_slug": lambda _model: "test-model",
                "is_supported_link": lambda _link: True,
                "pd": pd,
                "platform_for_url": adapter.detect_platform,
                "safe_str": lambda value: "" if value is None else str(value),
                "st": fake_st,
                "time": time,
                "timezone": timezone,
                "uuid": uuid,
            }
            runner = _load_runner(namespace)

            self.assertIsNone(
                runner(selected, "gemini-key", "apify-token", "test-model")
            )
            result = runner(
                selected,
                "gemini-key",
                "apify-token",
                "test-model",
            )

        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)
        self.assertEqual(len(tag_calls), 1)
        self.assertTrue(
            any("CHECKPOINT_STORAGE" in message for message in fake_st.errors)
        )


if __name__ == "__main__":
    unittest.main()
