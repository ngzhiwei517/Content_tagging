import unittest
import uuid

import requests

from taggy_cloud.job_store import (
    InMemoryCloudJobStore,
    JobConflictError,
    SupabaseCloudJobStore,
)


def post(number):
    return {
        "Link": f"https://www.tiktok.com/@creator/video/{1000 + number}",
        "Track": "Test track",
    }


def response(status, payload):
    item = requests.Response()
    item.status_code = status
    item.url = "https://example.supabase.co/rest/v1/test"
    item.headers["Content-Type"] = "application/json"
    item._content = __import__("json").dumps(payload).encode("utf-8")
    return item


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append(("get", args, kwargs))
        return self.responses.pop(0)

    def post(self, *args, **kwargs):
        self.calls.append(("post", args, kwargs))
        return self.responses.pop(0)


class CloudJobStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryCloudJobStore()
        self.job_id = uuid.uuid4().hex
        self.recovery_id = uuid.uuid4().hex

    def test_create_is_idempotent_but_rejects_different_payload(self):
        first = self.store.create_job(
            self.job_id,
            self.recovery_id,
            "gemini-test",
            [post(1), post(2)],
        )
        second = self.store.create_job(
            self.job_id,
            self.recovery_id,
            "gemini-test",
            [post(1), post(2)],
        )
        self.assertEqual(first["job_id"], second["job_id"])
        with self.assertRaises(JobConflictError):
            self.store.create_job(
                self.job_id,
                self.recovery_id,
                "gemini-test",
                [post(3)],
            )

    def test_completed_post_is_not_claimed_or_processed_again(self):
        self.store.create_job(
            self.job_id,
            self.recovery_id,
            "gemini-test",
            [post(1)],
        )
        worker = uuid.uuid4().hex
        claim = self.store.claim_post(self.job_id, 0, worker, 300)
        self.assertEqual("claimed", claim["state"])
        self.assertTrue(
            self.store.complete_post(
                self.job_id,
                0,
                worker,
                {"Creative Type": "Travel"},
            )
        )

        duplicate = self.store.claim_post(
            self.job_id,
            0,
            uuid.uuid4().hex,
            300,
        )
        self.assertEqual("completed", duplicate["state"])
        self.assertEqual("completed", self.store.summary(self.job_id)["status"])
        self.assertEqual(1, len(self.store.results(self.job_id)))

    def test_resume_keeps_completed_posts_and_resets_failed_post(self):
        self.store.create_job(
            self.job_id,
            self.recovery_id,
            "gemini-test",
            [post(1), post(2)],
        )
        first_worker = uuid.uuid4().hex
        self.store.claim_post(self.job_id, 0, first_worker, 300)
        self.store.complete_post(self.job_id, 0, first_worker, {"row": 1})

        second_worker = uuid.uuid4().hex
        self.store.claim_post(self.job_id, 1, second_worker, 300)
        self.store.fail_post(
            self.job_id,
            1,
            second_worker,
            "PROVIDER_ACCESS",
            retryable=False,
        )
        resumed = self.store.resume_job(self.job_id)

        self.assertEqual(1, resumed["dispatch_generation"])
        posts = self.store.list_posts(self.job_id)
        self.assertEqual("completed", posts[0]["status"])
        self.assertEqual("pending", posts[1]["status"])
        self.assertEqual(1, self.store.next_pending_position(self.job_id))

    def test_independent_jobs_can_hold_active_post_leases_together(self):
        other_job = uuid.uuid4().hex
        self.store.create_job(self.job_id, self.recovery_id, "model", [post(1)])
        self.store.create_job(other_job, uuid.uuid4().hex, "model", [post(2)])

        first = self.store.claim_post(self.job_id, 0, uuid.uuid4().hex, 300)
        second = self.store.claim_post(other_job, 0, uuid.uuid4().hex, 300)

        self.assertEqual("claimed", first["state"])
        self.assertEqual("claimed", second["state"])

    def test_supabase_retries_postgres_57014_before_returning_job(self):
        sleeps = []
        session = FakeSession(
            [
                response(400, {"code": "57014", "message": "cancelled"}),
                response(
                    200,
                    [
                        {
                            "job_id": self.job_id,
                            "recovery_id": self.recovery_id,
                            "model": "gemini-3.1-flash-lite",
                            "total_posts": 1,
                        }
                    ],
                ),
            ]
        )
        store = SupabaseCloudJobStore(
            "https://example.supabase.co",
            "server-key",
            session=session,
            retry_delays=(0.01,),
            sleep=sleeps.append,
        )
        job = store.get_job(self.job_id)
        self.assertEqual(self.job_id, job["job_id"])
        self.assertEqual([0.01], sleeps)

    def test_supabase_maps_job_id_conflict_to_safe_exception(self):
        session = FakeSession(
            [response(400, {"message": "TAGGY_JOB_CONFLICT"})]
        )
        store = SupabaseCloudJobStore(
            "https://example.supabase.co",
            "server-key",
            session=session,
            retry_delays=(),
        )
        with self.assertRaises(JobConflictError):
            store.create_job(
                self.job_id,
                self.recovery_id,
                "gemini-3.1-flash-lite",
                [post(1)],
            )

    def test_supabase_summary_fetches_status_without_post_payloads(self):
        session = FakeSession(
            [
                response(
                    200,
                    [
                        {
                            "job_id": self.job_id,
                            "recovery_id": self.recovery_id,
                            "model": "gemini-3.1-flash-lite",
                            "total_posts": 2,
                        }
                    ],
                ),
                response(200, [{"status": "completed"}, {"status": "running"}]),
            ]
        )
        store = SupabaseCloudJobStore(
            "https://example.supabase.co",
            "server-key",
            session=session,
            retry_delays=(),
        )

        summary = store.summary(self.job_id)

        self.assertEqual(1, summary["completed_posts"])
        self.assertEqual(1, summary["running_posts"])
        self.assertEqual("status", session.calls[1][2]["params"]["select"])


if __name__ == "__main__":
    unittest.main()
