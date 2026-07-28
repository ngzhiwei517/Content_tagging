import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from ugc_tagger.batch_checkpoint import (
    BatchCheckpointStore,
    dataframe_to_payload,
    input_fingerprint,
)


class BatchCheckpointStoreTests(unittest.TestCase):
    def sample_rows(self, count: int) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Platform": "Instagram Reels",
                    "Source": "Scale test",
                    "Link": f"https://www.instagram.com/reel/TEST{i:04d}",
                    "Market": "",
                    "Track": f"Track {i % 5}",
                    "Creator": f"creator_{i}",
                }
                for i in range(count)
            ]
        )

    def test_one_thousand_rows_complete_in_twenty_ordered_chunks(self):
        selected = self.sample_rows(1000)
        runtime_id = "a" * 32
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="scale-test",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            self.assertEqual(manifest["total_chunks"], 20)

            for chunk_index in range(7):
                chunk = store.chunk_frame(selected, manifest, chunk_index)
                tagged = chunk.assign(**{"Creative Type": "Others"})
                manifest = store.save_completed_chunk(
                    manifest,
                    chunk_index,
                    tagged,
                    elapsed_seconds=1.0,
                )

            # A new store instance simulates a new Streamlit script process.
            resumed_store = BatchCheckpointStore(Path(directory), chunk_size=50)
            resumed = resumed_store.find(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
            )
            self.assertIsNotNone(resumed)
            self.assertEqual(resumed["completed_rows"], 350)
            self.assertEqual(resumed_store.next_chunk_index(resumed), 7)

            manifest = resumed
            for chunk_index in range(7, 20):
                chunk = resumed_store.chunk_frame(selected, manifest, chunk_index)
                tagged = chunk.assign(**{"Creative Type": "Others"})
                manifest = resumed_store.save_completed_chunk(
                    manifest,
                    chunk_index,
                    tagged,
                    elapsed_seconds=1.0,
                )

            output = resumed_store.load_completed_results(manifest)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["completed_rows"], 1000)
            self.assertEqual(len(output), 1000)
            self.assertEqual(output.iloc[0]["Link"], selected.iloc[0]["Link"])
            self.assertEqual(output.iloc[-1]["Link"], selected.iloc[-1]["Link"])
            self.assertEqual(output["Link"].nunique(), 1000)

    def test_scraped_records_resume_without_persisting_secret_fields(self):
        selected = self.sample_rows(60)
        sentinel = "do-not-write-this-token"
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                "b" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="secret-test",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            records = [
                {
                    "url": selected.iloc[0]["Link"],
                    "caption": "Public caption",
                    "apify_token": sentinel,
                    "nested": {
                        "Authorization": sentinel,
                        "likesCount": 10,
                    },
                }
            ]
            store.save_scraped_records(manifest["job_id"], 0, records)

            raw_checkpoint = store._records_path(manifest["job_id"], 0).read_text(
                encoding="utf-8"
            )
            self.assertNotIn(sentinel, raw_checkpoint)
            restored = store.load_scraped_records(manifest["job_id"], 0)
            self.assertEqual(restored[0]["caption"], "Public caption")
            self.assertEqual(restored[0]["nested"]["likesCount"], 10)
            self.assertNotIn("apify_token", restored[0])
            self.assertNotIn("Authorization", restored[0]["nested"])

    def test_failure_manifest_does_not_persist_raw_exception_text(self):
        selected = self.sample_rows(60)
        sentinel = "do-not-write-this-token"
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                "d" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="failure-test",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            failed = store.mark_failed(
                manifest,
                f"Request failed with token {sentinel}",
            )
            raw_manifest = store._manifest_path(failed["job_id"]).read_text(
                encoding="utf-8"
            )
            self.assertNotIn(sentinel, raw_manifest)
            self.assertEqual(failed["status"], "failed")
            self.assertIn("Resume is required", failed["last_error"])

    def test_reconcile_recovers_a_chunk_written_before_manifest_update(self):
        selected = self.sample_rows(100)
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                "c" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="atomic-test",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            chunk = store.chunk_frame(selected, manifest, 0)
            store._atomic_write_json(
                store._chunk_path(manifest["job_id"], 0),
                dataframe_to_payload(chunk),
            )

            resumed = store.find(
                "c" * 32,
                selected,
                model="gemini-3.1-flash-lite",
            )
            self.assertEqual(resumed["completed_chunks"], [0])
            self.assertEqual(resumed["completed_rows"], 50)
            self.assertEqual(store.next_chunk_index(resumed), 1)

    def test_input_fingerprint_changes_with_order_or_model(self):
        rows = self.sample_rows(3)
        original = input_fingerprint(rows, "gemini-3.1-flash-lite")
        reordered = input_fingerprint(
            rows.iloc[::-1].reset_index(drop=True),
            "gemini-3.1-flash-lite",
        )
        other_model = input_fingerprint(rows, "gemini-3.5-flash")
        self.assertNotEqual(original, reordered)
        self.assertNotEqual(original, other_model)


class StreamlitLargeBatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path(__file__).resolve().parents[1] / "app.py"
        ).read_text(encoding="utf-8")

    def test_large_batch_uses_fifty_row_checkpoints_and_fresh_reruns(self):
        self.assertIn("DEFAULT_CHUNK_SIZE", self.source)
        self.assertIn("len(selected) > DEFAULT_CHUNK_SIZE", self.source)
        self.assertIn("store.save_completed_chunk(", self.source)
        self.assertIn("st.rerun()", self.source)

    def test_resume_is_explicit_after_an_interrupted_session(self):
        self.assertIn('start_label = "Resume tagging"', self.source)
        self.assertIn("Completed chunks are saved", self.source)


if __name__ == "__main__":
    unittest.main()
