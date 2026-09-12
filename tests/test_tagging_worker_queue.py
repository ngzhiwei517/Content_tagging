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
            "queue_position": 0,
            "active_recovery_id": "a" * 32,
            "lease_until": "2026-09-11T10:00:00Z",
            "active_workers": 1,
            "capacity": 3,
            "reason": "acquired",
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
    def test_local_fallback_allows_bounded_concurrent_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory))
            queue = TaggingWorkerQueue(store, max_workers=3)
            first = queue.claim("a" * 32, "b" * 32, "c" * 32)
            second = queue.claim("d" * 32, "e" * 32, "f" * 32)
            third = queue.claim("1" * 32, "2" * 32, "3" * 32)
            fourth = queue.claim("4" * 32, "5" * 32, "6" * 32)

            self.assertTrue(first.acquired)
            self.assertFalse(first.distributed)
            self.assertTrue(second.acquired)
            self.assertTrue(third.acquired)
            self.assertFalse(fourth.acquired)
            self.assertEqual(fourth.capacity, 3)

            queue.release("d" * 32, "e" * 32, "f" * 32)
            self.assertTrue(
                queue.claim("4" * 32, "5" * 32, "6" * 32).acquired
            )

    def test_persistent_backend_controls_admission_and_position(self):
        backend = FakeQueueBackend(
            {
                "acquired": False,
                "queue_position": 0,
                "active_recovery_id": "1" * 32,
                "lease_until": "2026-09-11T10:00:00Z",
                "active_workers": 3,
                "capacity": 3,
                "reason": "capacity_full",
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
            self.assertEqual(claim.queue_position, 0)
            self.assertEqual(claim.capacity, 3)
            self.assertEqual(claim.reason, "capacity_full")
            self.assertEqual(len(backend.claims), 1)
            self.assertEqual(backend.claims[0][3]["max_workers"], 3)

    def test_same_local_recovery_job_cannot_run_under_two_session_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = TaggingWorkerQueue(
                BatchCheckpointStore(Path(directory)),
                max_workers=3,
            )
            self.assertTrue(queue.claim("a" * 32, "b" * 32, "c" * 32).acquired)
            self.assertFalse(queue.claim("a" * 32, "b" * 32, "d" * 32).acquired)

    def test_worker_capacity_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory))
            self.assertEqual(TaggingWorkerQueue(store, max_workers=0).max_workers, 1)
            self.assertEqual(TaggingWorkerQueue(store, max_workers=99).max_workers, 16)

    def test_configured_persistence_fails_closed_without_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = TaggingWorkerQueue(
                BatchCheckpointStore(Path(directory)),
                persistent_required=True,
            )
            with self.assertRaises(TaggingWorkerQueueUnavailable):
                queue.claim("a" * 32, "b" * 32, "c" * 32)

    def test_app_claims_worker_slot_before_provider_work_and_releases_it(self):
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
        self.assertIn('auto_resume_action = "capacity_full"', step_four)
        self.assertIn("All {capacity} tagging workers are currently busy", APP_SOURCE)
        self.assertNotIn("queued at position", APP_SOURCE)
        self.assertIn("completed posts are saved", APP_SOURCE)

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

    def test_schema_defines_atomic_worker_pool_and_expiring_leases(self):
        self.assertIn("create table if not exists public.tagging_worker_slots", SCHEMA_SOURCE)
        self.assertIn("create or replace function public.tagging_pool_claim", SCHEMA_SOURCE)
        self.assertIn("pg_advisory_xact_lock", SCHEMA_SOURCE.lower())
        self.assertIn("lease_until", SCHEMA_SOURCE)
        self.assertIn("create or replace function public.tagging_pool_release", SCHEMA_SOURCE)
        self.assertIn("p_max_workers integer default 3", SCHEMA_SOURCE)


if __name__ == "__main__":
    unittest.main()
