"""Cloud Tasks dispatch with deterministic, retry-safe task names."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


class RecordingDispatcher:
    """Small deterministic dispatcher used by unit tests."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def dispatch(self, job_id: str, position: int, generation: int) -> str:
        call = {
            "job_id": job_id,
            "position": int(position),
            "generation": int(generation),
        }
        self.calls.append(call)
        return f"recorded/{job_id}/{position}/{generation}"


class GoogleCloudTasksDispatcher:
    """Submit one short post-processing request to a Cloud Tasks queue."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        queue: str,
        worker_url: str,
        task_api_key: str,
        service_account_email: str = "",
        deadline_seconds: int = 1800,
        client=None,
    ) -> None:
        self.project = str(project or "").strip()
        self.location = str(location or "").strip()
        self.queue = str(queue or "").strip()
        self.worker_url = str(worker_url or "").strip().rstrip("/")
        self.task_api_key = str(task_api_key or "").strip()
        self.service_account_email = str(service_account_email or "").strip()
        self.deadline_seconds = max(60, min(1800, int(deadline_seconds)))
        if not all(
            (
                self.project,
                self.location,
                self.queue,
                self.worker_url,
                self.task_api_key,
            )
        ):
            raise ValueError("Cloud Tasks dispatcher settings are incomplete.")
        if client is None:
            from google.cloud import tasks_v2

            client = tasks_v2.CloudTasksClient()
        self.client = client

    def dispatch(self, job_id: str, position: int, generation: int) -> str:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2

        parent = self.client.queue_path(self.project, self.location, self.queue)
        digest = hashlib.sha256(
            f"{job_id}:{int(position)}:{int(generation)}".encode("utf-8")
        ).hexdigest()[:40]
        task_name = self.client.task_path(
            self.project,
            self.location,
            self.queue,
            f"taggy-{digest}",
        )
        payload = json.dumps(
            {"job_id": job_id, "position": int(position)},
            separators=(",", ":"),
        ).encode("utf-8")
        http_request: Dict[str, Any] = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{self.worker_url}/internal/v1/tasks/tag-post",
            "headers": {
                "Content-Type": "application/json",
                "X-Taggy-Task-Key": self.task_api_key,
            },
            "body": payload,
        }
        if self.service_account_email:
            http_request["oidc_token"] = {
                "service_account_email": self.service_account_email,
                "audience": self.worker_url,
            }
        task = {
            "name": task_name,
            "http_request": http_request,
            "dispatch_deadline": duration_pb2.Duration(
                seconds=self.deadline_seconds
            ),
        }
        try:
            response = self.client.create_task(
                request={"parent": parent, "task": task}
            )
            return str(response.name)
        except AlreadyExists:
            # A deterministic name makes create/resume retries idempotent.
            return task_name


def dispatch_next(store, dispatcher, job_id: str) -> bool:
    """Dispatch the next pending row for one job, if one exists."""
    position = store.next_pending_position(job_id)
    if position is None:
        return False
    generation = int(store.get_job(job_id).get("dispatch_generation") or 0)
    dispatcher.dispatch(job_id, position, generation)
    return True
