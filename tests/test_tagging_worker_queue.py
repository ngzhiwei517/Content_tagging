import copy
import tempfile
import unittest
from pathlib import Path

from ugc_tagger.batch_checkpoint import BatchCheckpointStore
from ugc_tagger.tagging_worker_queue import (
    TaggingWorkerQueue,
    TaggingWorkerQueueUnavailable,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
SCHEMA_SOURCE = (ROOT / "checkpoint_schema.sql").read_text(encoding="utf-8")


class FakeQueueBackend:
    def __init__(self, payload=None):
        self.payload = payload or {
            "acquired": True,
            "queue_position": 1,
            "active_recovery_id": "a" * 32,
            "lease_until": "2026-09-11T10:00:00Z",
        }
        self.claims = []
        self.releases = []

    def claim_tagging_worker(self, recovery_id, job_id, owner_id, **kwargs):
        self.claims.append((recovery_id, job_id, owner_id, copy.deepcopy(kwargs)))
        return copy.deepcopy(self.payload)

    def release_tagging_worker(self, recovery_id, job_id, owner_id):
        self.releases.append((recovery_id, job_id, owner_id))
        return True


class RecordingObjectStore:
    def __init__(self):
        self.saved_keys = []

    def save(self, key, payload):
        self.saved_keys.append(key)

    def load(self, key):
        return None

    def list_prefix(self, prefix):
        return {}

    def delete(self, key):
        return None

    def delete_prefix(self, prefix):
        return None


class TaggingWorkerQueueTests(unittest.TestCase):
    def test_local_fallback_allows_only_one_job_at_a_time(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory))
            queue = TaggingWorkerQueue(store)
            first = queue.claim("a" * 32, "b" * 32, "c" * 32)
            second = queue.claim("d" * 32, "e" * 32, "f" * 32)

            self.assertTrue(first.acquired)
            self.assertFalse(first.distributed)
            self.assertFalse(second.acquired)

            queue.release("d" * 32, "e" * 32, "f" * 32)
            self.assertFalse(
                queue.claim("d" * 32, "e" * 32, "f" * 32).acquired
            )
            queue.release("a" * 32, "b" * 32, "c" * 32)
            self.assertTrue(
                queue.claim("d" * 32, "e" * 32, "f" * 32).acquired
            )

    def test_persistent_backend_controls_admission_and_position(self):
        backend = FakeQueueBackend(
            {
                "acquired": False,
                "queue_position": 3,
                "active_recovery_id": "1" * 32,
                "lease_until": "2026-09-11T10:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            queue = TaggingWorkerQueue(
                BatchCheckpointStore(Path(directory)),
                persistent_backend=backend,
                persistent_required=True,
            )
            claim = queue.claim("a" * 32, "b" * 32, "c" * 32)

            self.assertFalse(claim.acquired)
            self.assertTrue(claim.distributed)
            self.assertEqual(claim.queue_position, 3)
            self.assertEqual(len(backend.claims), 1)

    def test_configured_persistence_fails_closed_without_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = TaggingWorkerQueue(
                BatchCheckpointStore(Path(directory)),
                persistent_required=True,
            )
            with self.assertRaises(TaggingWorkerQueueUnavailable):
                queue.claim("a" * 32, "b" * 32, "c" * 32)

    def test_app_claims_global_worker_before_provider_work_and_releases_it(self):
        step_four = APP_SOURCE.split("# STEP 4: Run tagging", 1)[1].split(
            "# STEP 5: Review",
            1,
        )[0]
        self.assertIn("worker_queue.claim(", step_four)
        self.assertIn("worker_queue.release(", step_four)
        self.assertLess(
            step_four.index("worker_queue.claim("),
            step_four.index("run_real_tagging_backend(selected)"),
        )
        self.assertIn('auto_resume_action = "queue_wait"', step_four)
        self.assertIn("skips completed posts", APP_SOURCE)

    def test_per_post_objects_replace_periodic_full_partial_snapshots(self):
        runner = APP_SOURCE.split(
            "def _run_checkpointed_tag_every_link_v68_43",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertIn("store.save_partial_row(", runner)
        self.assertNotIn("store.save_partial_snapshot(", runner)
        self.assertNotIn("REMOTE_PARTIAL_SNAPSHOT_INTERVAL", APP_SOURCE)

    def test_saving_five_results_makes_five_small_remote_row_writes(self):
        remote = RecordingObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(
                Path(directory),
                persistent_store=remote,
            )
            for position in range(5):
                store.save_partial_row(
                    "a" * 32,
                    0,
                    position,
                    {"Link": f"https://example.com/{position}", "Creative Type": "Others"},
                )

        self.assertEqual(len(remote.saved_keys), 5)
        self.assertTrue(all("/row_" in key for key in remote.saved_keys))
        self.assertFalse(any(key.endswith("snapshot.json") for key in remote.saved_keys))

    def test_schema_defines_atomic_fifo_queue_and_expiring_lease(self):
        self.assertIn("create table if not exists public.tagging_job_queue", SCHEMA_SOURCE)
        self.assertIn("create table if not exists public.tagging_worker_lease", SCHEMA_SOURCE)
        self.assertIn("create or replace function public.tagging_queue_claim", SCHEMA_SOURCE)
        self.assertIn("for update", SCHEMA_SOURCE.lower())
        self.assertIn("lease_until", SCHEMA_SOURCE)
        self.assertIn("create or replace function public.tagging_queue_release", SCHEMA_SOURCE)


if __name__ == "__main__":
    unittest.main()
