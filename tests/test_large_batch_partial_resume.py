import copy
import json
import shutil
import tempfile
import unittest
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ugc_tagger.batch_checkpoint import BatchCheckpointStore
from ugc_tagger.final_update2_adapter import tag_candidates


class MemoryCheckpointObjects:
    """Small persistent-object stand-in for an app restart test."""

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


class LargeBatchPartialResumeTests(unittest.TestCase):
    def test_two_hundred_rows_resume_after_twenty_without_duplicate_analysis(self):
        selected = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Source": "Scale test",
                "Link": f"https://www.tiktok.com/@creator/video/{900000 + index}",
                "Market": "SG",
                "Track": "Scale track",
                "Creator": f"creator_{index}",
            }
            for index in range(200)
        ])
        records = [
            {
                "id": str(900000 + index),
                "webVideoUrl": selected.loc[index, "Link"],
            }
            for index in range(200)
        ]

        class InterruptOnceBackend:
            calls = Counter()
            completed_before_interrupt = 0
            interrupted = False

            @staticmethod
            @contextmanager
            def gemini_model_context(_model):
                yield _model

            @classmethod
            def run_pipeline(cls, group_records, *_args, **kwargs):
                callback = kwargs["on_row_done"]
                outputs = []
                for position, record in enumerate(group_records):
                    if not cls.interrupted and cls.completed_before_interrupt >= 20:
                        cls.interrupted = True
                        raise RuntimeError("simulated quota interruption")
                    link = record["webVideoUrl"]
                    cls.calls[link] += 1
                    output = {
                        "tiktok_url": link,
                        "Creative Type": "Others",
                        "Content Details": "Synthetic completed row",
                        "validation_status": "accepted",
                        "tier_used": "tier1_cover",
                    }
                    outputs.append(output)
                    callback(
                        position + 1,
                        len(group_records),
                        output,
                        "tier1_cover",
                    )
                    if not cls.interrupted:
                        cls.completed_before_interrupt += 1
                return pd.DataFrame(outputs)

        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                "a" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="integration-resume",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )

            def process_chunk(chunk_index):
                nonlocal manifest
                chunk = store.chunk_frame(selected, manifest, chunk_index)
                positions = store.partial_positions(manifest["job_id"], chunk_index)
                remaining_positions = [
                    position
                    for position in range(len(chunk))
                    if position not in set(positions)
                ]
                remaining = chunk.iloc[remaining_positions].reset_index(drop=True)
                chunk_records = records[
                    chunk_index * 50:(chunk_index + 1) * 50
                ]

                def save_result(input_position, row, _tier):
                    store.save_partial_row(
                        manifest["job_id"],
                        chunk_index,
                        remaining_positions[input_position],
                        row,
                    )

                if not remaining.empty:
                    tag_candidates(
                        remaining,
                        chunk_records,
                        "key",
                        "token",
                        on_result=save_result,
                    )
                partial = store.load_partial_chunk_results(
                    manifest["job_id"],
                    chunk_index,
                )
                self.assertEqual(len(partial), len(chunk))
                manifest = store.save_completed_chunk(
                    manifest,
                    chunk_index,
                    partial.drop(
                        columns=["_checkpoint_row_position"],
                        errors="ignore",
                    ),
                    elapsed_seconds=1.0,
                )

            with patch(
                "ugc_tagger.final_update2_adapter.load_backend",
                return_value=InterruptOnceBackend(),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "simulated quota interruption",
                ):
                    process_chunk(0)
                manifest = store.mark_paused(manifest, quota=True)
                self.assertEqual(manifest["saved_rows"], 20)

                resumed_store = BatchCheckpointStore(Path(directory), chunk_size=50)
                resumed = resumed_store.find(
                    "a" * 32,
                    selected,
                    model="gemini-3.1-flash-lite",
                )
                self.assertEqual(resumed["saved_rows"], 20)
                store = resumed_store
                manifest = resumed

                process_chunk(0)
                for chunk_index in range(1, 4):
                    process_chunk(chunk_index)

            output = store.load_completed_results(manifest)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(len(output), 200)
            self.assertEqual(output["Link"].tolist(), selected["Link"].tolist())
            self.assertTrue(all(count == 1 for count in InterruptOnceBackend.calls.values()))
            self.assertEqual(len(InterruptOnceBackend.calls), 200)

    def test_253_rows_resume_after_restart_with_a_replacement_key(self):
        selected = pd.DataFrame([
            {
                "Platform": "TikTok",
                "Source": "253-post restart test",
                "Link": f"https://www.tiktok.com/@creator/video/{950000 + index}",
                "Market": "SG",
                "Track": "Restart track",
                "Creator": f"creator_{index}",
            }
            for index in range(253)
        ])
        records = [
            {
                "id": str(950000 + index),
                "webVideoUrl": selected.loc[index, "Link"],
            }
            for index in range(253)
        ]

        class QuotaThenReplacementBackend:
            calls = Counter()
            keys_by_link = {}
            completed_with_old_key = 0
            interrupted = False

            @staticmethod
            @contextmanager
            def gemini_model_context(_model):
                yield _model

            @classmethod
            def run_pipeline(cls, group_records, *_args, **kwargs):
                gemini_key = _args[1]
                callback = kwargs["on_row_done"]
                outputs = []
                for position, record in enumerate(group_records):
                    if (
                        gemini_key == "exhausted-key"
                        and not cls.interrupted
                        and cls.completed_with_old_key >= 20
                    ):
                        cls.interrupted = True
                        raise RuntimeError("429 RESOURCE_EXHAUSTED")
                    link = record["webVideoUrl"]
                    cls.calls[link] += 1
                    cls.keys_by_link[link] = gemini_key
                    output = {
                        "tiktok_url": link,
                        "Creative Type": "Others",
                        "Content Details": "Synthetic completed row",
                        "validation_status": "accepted",
                        "tier_used": "tier1_cover",
                    }
                    outputs.append(output)
                    callback(position + 1, len(group_records), output, "tier1_cover")
                    if gemini_key == "exhausted-key":
                        cls.completed_with_old_key += 1
                return pd.DataFrame(outputs)

        remote = MemoryCheckpointObjects()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"
            store = BatchCheckpointStore(
                root,
                chunk_size=50,
                persistent_store=remote,
            )
            manifest = store.prepare(
                "b" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="quota-resume-test",
                comparison_started_utc="2026-08-03T00:00:00+00:00",
            )

            def process_chunk(chunk_index, gemini_key):
                nonlocal manifest, store
                chunk = store.chunk_frame(selected, manifest, chunk_index)
                saved_positions = set(
                    store.partial_positions(manifest["job_id"], chunk_index)
                )
                remaining_positions = [
                    position
                    for position in range(len(chunk))
                    if position not in saved_positions
                ]
                remaining = chunk.iloc[remaining_positions].reset_index(drop=True)
                chunk_records = records[
                    chunk_index * 50:(chunk_index + 1) * 50
                ]

                def save_result(input_position, row, _tier):
                    store.save_partial_row(
                        manifest["job_id"],
                        chunk_index,
                        remaining_positions[input_position],
                        row,
                    )

                if not remaining.empty:
                    tag_candidates(
                        remaining,
                        chunk_records,
                        gemini_key,
                        "apify-test-token",
                        on_result=save_result,
                    )
                partial = store.load_partial_chunk_results(
                    manifest["job_id"],
                    chunk_index,
                )
                self.assertEqual(len(partial), len(chunk))
                manifest = store.save_completed_chunk(
                    manifest,
                    chunk_index,
                    partial.drop(
                        columns=["_checkpoint_row_position"],
                        errors="ignore",
                    ),
                    elapsed_seconds=1.0,
                )

            with patch(
                "ugc_tagger.final_update2_adapter.load_backend",
                return_value=QuotaThenReplacementBackend(),
            ):
                with self.assertRaisesRegex(RuntimeError, "RESOURCE_EXHAUSTED"):
                    process_chunk(0, "exhausted-key")
                manifest = store.mark_paused(manifest, quota=True)
                self.assertEqual(manifest["status"], "paused_quota")
                self.assertEqual(manifest["saved_rows"], 20)

                # Simulate Streamlit/container restart: only the persistent
                # checkpoint objects survive, then the owner supplies a new key.
                shutil.rmtree(root)
                store = BatchCheckpointStore(
                    root,
                    chunk_size=50,
                    persistent_store=remote,
                )
                manifest = store.find(
                    "b" * 32,
                    selected,
                    model="gemini-3.1-flash-lite",
                )
                self.assertEqual(manifest["saved_rows"], 20)

                process_chunk(0, "replacement-key")
                for chunk_index in range(1, 6):
                    process_chunk(chunk_index, "replacement-key")

            output = store.load_completed_results(manifest)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(len(output), 253)
            self.assertEqual(output["Link"].tolist(), selected["Link"].tolist())
            self.assertTrue(
                all(count == 1 for count in QuotaThenReplacementBackend.calls.values())
            )
            self.assertEqual(len(QuotaThenReplacementBackend.calls), 253)
            for link in selected["Link"].iloc[:20]:
                self.assertEqual(
                    QuotaThenReplacementBackend.keys_by_link[link],
                    "exhausted-key",
                )
            for link in selected["Link"].iloc[20:]:
                self.assertEqual(
                    QuotaThenReplacementBackend.keys_by_link[link],
                    "replacement-key",
                )

            persisted = json.dumps(remote.objects)
            self.assertNotIn("exhausted-key", persisted)
            self.assertNotIn("replacement-key", persisted)
            self.assertNotIn("apify-test-token", persisted)


if __name__ == "__main__":
    unittest.main()
