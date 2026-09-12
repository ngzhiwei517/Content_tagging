import threading
import time
import unittest

from ugc_tagger.async_checkpoint import AsyncCheckpointWriter


class AsyncCheckpointWriterTests(unittest.TestCase):
    def test_ten_sessions_enqueue_without_waiting_for_remote_capacity(self):
        writer = AsyncCheckpointWriter(max_workers=4)
        release = threading.Event()
        four_started = threading.Event()
        started_count = 0
        started_lock = threading.Lock()

        def slow_save():
            nonlocal started_count
            with started_lock:
                started_count += 1
                if started_count == 4:
                    four_started.set()
            release.wait(timeout=3)

        futures = []
        try:
            before = time.perf_counter()
            for position in range(10):
                futures.append(
                    writer.submit(
                        f"run-{position}",
                        f"digest-{position}",
                        slow_save,
                    )
                )
            elapsed = time.perf_counter() - before

            self.assertLess(elapsed, 0.5)
            self.assertTrue(four_started.wait(timeout=1))
            release.set()
            self.assertTrue(
                all(future.result(timeout=3) == "saved" for future in futures)
            )
        finally:
            release.set()
            writer.shutdown()

    def test_slow_remote_save_does_not_block_the_calling_session(self):
        writer = AsyncCheckpointWriter(max_workers=2)
        started = threading.Event()
        release = threading.Event()

        def slow_save():
            started.set()
            release.wait(timeout=2)

        try:
            before = time.perf_counter()
            future = writer.submit("run-a", "digest-a", slow_save)
            elapsed = time.perf_counter() - before

            self.assertLess(elapsed, 0.2)
            self.assertTrue(started.wait(timeout=1))
            self.assertFalse(future.done())
            release.set()
            self.assertEqual(future.result(timeout=2), "saved")
            self.assertEqual(writer.status("run-a")["saved_digest"], "digest-a")
        finally:
            release.set()
            writer.shutdown()

    def test_different_recovery_ids_save_concurrently(self):
        writer = AsyncCheckpointWriter(max_workers=2)
        first_started = threading.Event()
        second_started = threading.Event()
        release = threading.Event()

        def first_save():
            first_started.set()
            release.wait(timeout=2)

        def second_save():
            second_started.set()
            release.wait(timeout=2)

        try:
            first = writer.submit("run-a", "digest-a", first_save)
            second = writer.submit("run-b", "digest-b", second_save)
            self.assertTrue(first_started.wait(timeout=1))
            self.assertTrue(second_started.wait(timeout=1))
            self.assertFalse(first.done())
            self.assertFalse(second.done())
            release.set()
            self.assertEqual(first.result(timeout=2), "saved")
            self.assertEqual(second.result(timeout=2), "saved")
        finally:
            release.set()
            writer.shutdown()

    def test_same_recovery_id_keeps_only_the_newest_pending_state(self):
        writer = AsyncCheckpointWriter(max_workers=1)
        first_started = threading.Event()
        release = threading.Event()
        writes = []

        def first_save():
            writes.append("first")
            first_started.set()
            release.wait(timeout=2)

        try:
            first = writer.submit("run-a", "digest-1", first_save)
            self.assertTrue(first_started.wait(timeout=1))
            replaced = writer.submit(
                "run-a", "digest-2", lambda: writes.append("replaced")
            )
            newest = writer.submit(
                "run-a", "digest-3", lambda: writes.append("newest")
            )

            self.assertEqual(replaced.result(timeout=1), "superseded")
            release.set()
            self.assertEqual(first.result(timeout=2), "saved")
            self.assertEqual(newest.result(timeout=2), "saved")
            self.assertEqual(writes, ["first", "newest"])
            self.assertEqual(writer.status("run-a")["saved_digest"], "digest-3")
        finally:
            release.set()
            writer.shutdown()


if __name__ == "__main__":
    unittest.main()
