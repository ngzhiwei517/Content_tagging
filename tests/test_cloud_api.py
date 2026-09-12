import unittest
import uuid

from fastapi.testclient import TestClient

from taggy_cloud.api import create_app
from taggy_cloud.config import CloudBackendSettings
from taggy_cloud.dispatcher import RecordingDispatcher
from taggy_cloud.job_store import InMemoryCloudJobStore


class FakeProcessor:
    def __init__(self):
        self.calls = []

    def process(self, post, model):
        self.calls.append((dict(post), model))
        return {
            **post,
            "Creative Type": "Travel",
            "Final Labels": "Travel",
        }


class TimeoutProcessor:
    def process(self, post, model):
        raise TimeoutError("provider timeout")


class FailOnceOnSecondDispatch(RecordingDispatcher):
    def __init__(self):
        super().__init__()
        self.failed = False

    def dispatch(self, job_id, position, generation):
        if int(position) == 1 and not self.failed:
            self.failed = True
            raise ConnectionError("temporary Cloud Tasks failure")
        return super().dispatch(job_id, position, generation)


class CloudApiTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryCloudJobStore()
        self.dispatcher = RecordingDispatcher()
        self.processor = FakeProcessor()
        self.settings = CloudBackendSettings(
            backend_api_key="backend-secret",
            task_api_key="task-secret",
            local_mode=True,
            max_posts_per_job=100,
            max_post_attempts=2,
        )
        self.app = create_app(
            settings=self.settings,
            store=self.store,
            dispatcher=self.dispatcher,
            processor=self.processor,
        )
        self.client = TestClient(self.app)
        self.job_id = uuid.uuid4().hex
        self.recovery_id = uuid.uuid4().hex
        self.posts = [
            {
                "Link": "https://www.tiktok.com/@creator/video/1234567890",
                "Track": "Test track",
            },
            {
                "Link": "https://www.instagram.com/reel/ABC123xyz/",
                "Track": "Test track",
            },
        ]

    @property
    def backend_headers(self):
        return {"X-Taggy-Backend-Key": "backend-secret"}

    @property
    def task_headers(self):
        return {"X-Taggy-Task-Key": "task-secret"}

    def create_job(self):
        return self.client.post(
            "/v1/jobs",
            headers=self.backend_headers,
            json={
                "job_id": self.job_id,
                "recovery_id": self.recovery_id,
                "model": "gemini-3.1-flash-lite",
                "posts": self.posts,
            },
        )

    def test_api_rejects_missing_backend_key(self):
        response = self.client.get(f"/v1/jobs/{self.job_id}")
        self.assertEqual(401, response.status_code)

    def test_api_rejects_unapproved_model(self):
        response = self.client.post(
            "/v1/jobs",
            headers=self.backend_headers,
            json={
                "job_id": self.job_id,
                "recovery_id": self.recovery_id,
                "model": "unexpected-model",
                "posts": self.posts,
            },
        )
        self.assertEqual(422, response.status_code)
        self.assertEqual([], self.dispatcher.calls)

    def test_api_sanitizes_job_input_even_for_direct_callers(self):
        self.posts[0]["api_token"] = "must-not-be-stored"
        response = self.create_job()
        self.assertEqual(202, response.status_code)
        stored = self.store.list_posts(self.job_id)[0]["input_payload"]
        self.assertNotIn("api_token", stored)

    def test_one_active_post_per_job_chains_until_complete(self):
        response = self.create_job()
        self.assertEqual(202, response.status_code)
        self.assertEqual([0], [call["position"] for call in self.dispatcher.calls])

        first = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual(200, first.status_code)
        self.assertEqual([0, 1], [call["position"] for call in self.dispatcher.calls])

        second = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 1},
        )
        self.assertEqual(200, second.status_code)

        status_response = self.client.get(
            f"/v1/jobs/{self.job_id}", headers=self.backend_headers
        )
        self.assertEqual("completed", status_response.json()["status"])
        results_response = self.client.get(
            f"/v1/jobs/{self.job_id}/results", headers=self.backend_headers
        )
        results = results_response.json()["results"]
        self.assertEqual(2, len(results))
        self.assertEqual(2, len(self.processor.calls))

        duplicate = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual("already_completed", duplicate.json()["status"])
        self.assertEqual(2, len(self.processor.calls))

    def test_temporary_failure_retries_then_pauses_without_losing_state(self):
        self.app.state.runtime.processor = TimeoutProcessor()
        self.create_job()
        first = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual(503, first.status_code)
        summary = self.store.summary(self.job_id)
        self.assertEqual("retrying", summary["status"])
        self.assertEqual(1, summary["retryable_posts"])

        second = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual(200, second.status_code)
        summary = self.store.summary(self.job_id)
        self.assertEqual("needs_attention", summary["status"])
        self.assertEqual(1, summary["failed_posts"])

    def test_resume_preserves_completed_result_and_dispatches_failed_position(self):
        self.create_job()
        self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        worker = uuid.uuid4().hex
        self.store.claim_post(self.job_id, 1, worker, 300)
        self.store.fail_post(
            self.job_id,
            1,
            worker,
            "PROVIDER_ACCESS",
            retryable=False,
        )

        response = self.client.post(
            f"/v1/jobs/{self.job_id}/resume",
            headers=self.backend_headers,
        )
        self.assertEqual(202, response.status_code)
        self.assertEqual(1, response.json()["completed_posts"])
        self.assertEqual(1, self.dispatcher.calls[-1]["position"])
        self.assertEqual(1, self.dispatcher.calls[-1]["generation"])

    def test_dispatch_failure_retries_without_reprocessing_completed_post(self):
        dispatcher = FailOnceOnSecondDispatch()
        self.app.state.runtime.dispatcher = dispatcher
        self.create_job()

        first = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual(503, first.status_code)
        self.assertEqual(1, self.store.summary(self.job_id)["completed_posts"])
        self.assertEqual(1, len(self.processor.calls))

        retry = self.client.post(
            "/internal/v1/tasks/tag-post",
            headers=self.task_headers,
            json={"job_id": self.job_id, "position": 0},
        )
        self.assertEqual(200, retry.status_code)
        self.assertEqual("already_completed", retry.json()["status"])
        self.assertEqual(1, len(self.processor.calls))
        self.assertEqual(1, dispatcher.calls[-1]["position"])


if __name__ == "__main__":
    unittest.main()
