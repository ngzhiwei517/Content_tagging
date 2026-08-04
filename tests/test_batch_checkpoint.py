import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ugc_tagger.batch_checkpoint import (
    BatchCheckpointStore,
    dataframe_to_payload,
    input_fingerprint,
)


class BatchCheckpointStoreTests(unittest.TestCase):
    def test_atomic_local_write_retries_a_transient_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "checkpoint.json"
            real_replace = __import__("os").replace
            attempts = 0

            def transient_replace(source, target):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("temporarily locked")
                return real_replace(source, target)

            with patch(
                "ugc_tagger.batch_checkpoint.os.replace",
                side_effect=transient_replace,
            ), patch("ugc_tagger.batch_checkpoint.time.sleep") as sleep:
                BatchCheckpointStore._write_local_json(
                    destination,
                    {"saved_rows": 5},
                )

            self.assertEqual(attempts, 3)
            self.assertEqual(json.loads(destination.read_text()), {"saved_rows": 5})
            self.assertEqual(sleep.call_count, 2)

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
            self.assertEqual(failed["status"], "paused_error")
            self.assertIn("Resume is required", failed["last_error"])

    def test_twenty_partial_rows_resume_without_repeating_them(self):
        selected = self.sample_rows(200)
        runtime_id = "e" * 32
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="partial-test",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            first_chunk = store.chunk_frame(selected, manifest, 0)
            for position in range(20):
                store.save_partial_row(
                    manifest["job_id"],
                    0,
                    position,
                    first_chunk.iloc[position].to_dict()
                    | {"Creative Type": "Others"},
                )
            paused = store.mark_paused(manifest, quota=True)

            resumed_store = BatchCheckpointStore(Path(directory), chunk_size=50)
            resumed = resumed_store.find(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
            )
            self.assertEqual(paused["status"], "paused_quota")
            self.assertEqual(resumed["saved_rows"], 20)
            self.assertEqual(resumed["partial_rows"], 20)
            self.assertEqual(resumed_store.partial_positions(resumed["job_id"], 0), list(range(20)))
            saved = resumed_store.load_saved_results(resumed)
            self.assertEqual(len(saved), 20)
            self.assertEqual(saved["Link"].tolist(), selected.iloc[:20]["Link"].tolist())

    def test_completed_chunk_replaces_partial_rows_atomically(self):
        selected = self.sample_rows(60)
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                "f" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="partial-finalise",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            chunk = store.chunk_frame(selected, manifest, 0).assign(
                **{"Creative Type": "Others"}
            )
            for position, (_, row) in enumerate(chunk.iterrows()):
                store.save_partial_row(manifest["job_id"], 0, position, row)
            manifest = store.save_completed_chunk(
                manifest,
                0,
                chunk,
                elapsed_seconds=1.0,
            )
            self.assertEqual(manifest["completed_rows"], 50)
            self.assertEqual(manifest["saved_rows"], 50)
            self.assertEqual(store.partial_positions(manifest["job_id"], 0), [])
            self.assertEqual(len(store.load_completed_results(manifest)), 50)

    def test_same_input_is_isolated_between_runtime_ids(self):
        selected = self.sample_rows(60)
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            first = store.prepare(
                "1" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="first-user",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            second = store.prepare(
                "2" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="second-user",
                comparison_started_utc="2026-07-28T00:00:00+00:00",
            )
            self.assertNotEqual(first["job_id"], second["job_id"])
            store.save_partial_row(
                first["job_id"],
                0,
                0,
                selected.iloc[0].to_dict(),
            )
            self.assertEqual(store.partial_positions(first["job_id"], 0), [0])
            self.assertEqual(store.partial_positions(second["job_id"], 0), [])

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
        self.assertIn("MAX_LIVE_POSTS_PER_EXECUTION_V68_52 = 5", self.source)
        self.assertIn("REMOTE_PARTIAL_SNAPSHOT_INTERVAL_V68_52 = 25", self.source)
        self.assertIn(
            ":MAX_LIVE_POSTS_PER_EXECUTION_V68_52",
            self.source.replace(" ", "").replace("\n", ""),
        )
        self.assertIn("store.save_completed_chunk(", self.source)
        self.assertIn("store.save_partial_row(", self.source)
        self.assertIn("persist_remote=False", self.source)
        self.assertIn("store.save_partial_snapshot(", self.source)
        self.assertIn("on_result=on_result", self.source)
        self.assertIn("st.rerun()", self.source)

    def test_incomplete_micro_batch_yields_without_marking_an_error(self):
        self.assertIn("completed_rows + len(actual_positions)", self.source)
        self.assertIn('"continuing safely"', self.source)
        self.assertNotIn('raise RuntimeError("PARTIAL_CHECKPOINT_INCOMPLETE")', self.source)

    def test_resume_is_explicit_after_an_interrupted_session(self):
        self.assertIn('start_label = "Resume tagging"', self.source)
        self.assertIn("completed posts are saved", self.source)

    def test_post_specific_failure_is_isolated_before_pausing_batch(self):
        self.assertIn(
            "def _tag_remaining_with_row_isolation_v68_43(",
            self.source,
        )
        self.assertIn(
            "_failed_analysis_review_row_v68_43(single.iloc[0])",
            self.source,
        )
        self.assertIn("diagnostic code {error_code}", self.source)

    def test_new_failure_helper_is_not_a_fragile_module_level_import(self):
        import_block = self.source.split(
            "from ugc_tagger.final_update2_adapter import (",
            1,
        )[1].split(")", 1)[0]
        self.assertNotIn("failed_analysis_review_row", import_block)
        self.assertIn(
            'getattr(_final_update2_adapter, "failed_analysis_review_row", None)',
            self.source,
        )

    def test_server_managed_secrets_open_directly_on_add_posts(self):
        self.assertIn('_managed_api_secret_v68_43("GEMINI_API_KEY")', self.source)
        self.assertIn('_managed_api_secret_v68_43("APIFY_TOKEN")', self.source)
        self.assertIn('"step": 2', self.source)
        self.assertIn('(2, "01", "Add Posts", "Files or links")', self.source)
        self.assertNotIn('(1, "01", "API Keys", "Setup")', self.source)
        self.assertIn("Contact the app owner to update", self.source)


if __name__ == "__main__":
    unittest.main()
