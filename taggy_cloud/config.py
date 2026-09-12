"""Environment-only configuration for the optional Taggy cloud backend."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _text(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(_text(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class CloudBackendSettings:
    """Server settings loaded without copying credentials into job payloads."""

    backend_api_key: str = ""
    task_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "asia-southeast1"
    cloud_tasks_queue: str = "taggy-posts"
    worker_url: str = ""
    task_service_account: str = ""
    max_posts_per_job: int = 100
    max_post_attempts: int = 5
    task_deadline_seconds: int = 1800
    post_lease_seconds: int = 2100
    local_mode: bool = False

    @classmethod
    def from_env(cls) -> "CloudBackendSettings":
        local_mode = _text("TAGGY_CLOUD_LOCAL_MODE").casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            backend_api_key=_text("TAGGY_BACKEND_API_KEY"),
            task_api_key=_text("TAGGY_TASK_API_KEY"),
            supabase_url=_text("CHECKPOINT_SUPABASE_URL"),
            supabase_key=_text("CHECKPOINT_SUPABASE_KEY"),
            google_cloud_project=_text("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=_text(
                "GOOGLE_CLOUD_LOCATION", "asia-southeast1"
            ),
            cloud_tasks_queue=_text("TAGGY_CLOUD_TASKS_QUEUE", "taggy-posts"),
            worker_url=_text("TAGGY_CLOUD_WORKER_URL"),
            task_service_account=_text("TAGGY_TASK_SERVICE_ACCOUNT"),
            max_posts_per_job=_integer("TAGGY_MAX_POSTS_PER_JOB", 100, 1, 500),
            max_post_attempts=_integer("TAGGY_MAX_POST_ATTEMPTS", 5, 1, 10),
            task_deadline_seconds=_integer(
                "TAGGY_TASK_DEADLINE_SECONDS", 1800, 60, 1800
            ),
            post_lease_seconds=_integer(
                "TAGGY_POST_LEASE_SECONDS", 2100, 120, 3600
            ),
            local_mode=local_mode,
        )

    @property
    def storage_ready(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def dispatcher_ready(self) -> bool:
        return bool(
            self.google_cloud_project
            and self.google_cloud_location
            and self.cloud_tasks_queue
            and self.worker_url
        )

    @property
    def production_ready(self) -> bool:
        return bool(
            self.backend_api_key
            and self.task_api_key
            and self.storage_ready
            and self.dispatcher_ready
        )
