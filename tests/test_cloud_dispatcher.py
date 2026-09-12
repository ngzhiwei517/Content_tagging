import json
import types
import unittest

from taggy_cloud.dispatcher import GoogleCloudTasksDispatcher


class FakeTasksClient:
    def __init__(self):
        self.requests = []

    def queue_path(self, project, location, queue):
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def task_path(self, project, location, queue, task):
        return f"{self.queue_path(project, location, queue)}/tasks/{task}"

    def create_task(self, *, request):
        self.requests.append(request)
        return types.SimpleNamespace(name=request["task"]["name"])


class CloudDispatcherTests(unittest.TestCase):
    def test_task_is_bounded_minimal_and_deterministically_named(self):
        client = FakeTasksClient()
        dispatcher = GoogleCloudTasksDispatcher(
            project="taggy-test",
            location="asia-southeast1",
            queue="taggy-posts",
            worker_url="https://backend.example",
            task_api_key="task-secret",
            deadline_seconds=1800,
            client=client,
        )
        job_id = "a" * 32

        first_name = dispatcher.dispatch(job_id, 4, 2)
        second_name = dispatcher.dispatch(job_id, 4, 2)

        self.assertEqual(first_name, second_name)
        task = client.requests[0]["task"]
        request = task["http_request"]
        self.assertEqual(
            {"job_id": job_id, "position": 4},
            json.loads(request["body"].decode("utf-8")),
        )
        self.assertEqual(
            "https://backend.example/internal/v1/tasks/tag-post",
            request["url"],
        )
        self.assertEqual("task-secret", request["headers"]["X-Taggy-Task-Key"])
        self.assertEqual(1800, task["dispatch_deadline"].seconds)


if __name__ == "__main__":
    unittest.main()
