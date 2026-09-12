"""FastAPI control plane and Cloud Tasks worker endpoint for Taggy."""

from __future__ import annotations

import hmac
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from ugc_tagger.instagram_reels_adapter import is_supported_post_url
from ugc_tagger.model_comparison import SUPPORTED_GEMINI_MODELS

from .config import CloudBackendSettings
from .dispatcher import GoogleCloudTasksDispatcher, RecordingDispatcher, dispatch_next
from .job_store import (
    InMemoryCloudJobStore,
    JobConflictError,
    JobNotFoundError,
    SupabaseCloudJobStore,
    validate_id,
)
from .processor import (
    TaggyPostProcessor,
    error_is_retryable,
    safe_processing_error_code,
)
from .sanitize import sanitize_mapping


class CreateJobRequest(BaseModel):
    job_id: str
    recovery_id: str
    model: str
    posts: List[Dict[str, Any]] = Field(default_factory=list)


class TaskRequest(BaseModel):
    job_id: str
    position: int = Field(ge=0)


@dataclass
class Runtime:
    settings: CloudBackendSettings
    store: Any
    dispatcher: Any
    processor: Optional[Any]


def _constant_time_match(actual: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(
        str(actual or "").encode("utf-8"),
        str(expected).encode("utf-8"),
    )


def _build_runtime(settings: CloudBackendSettings) -> Runtime:
    if settings.storage_ready:
        store = SupabaseCloudJobStore(settings.supabase_url, settings.supabase_key)
    elif settings.local_mode:
        store = InMemoryCloudJobStore()
    else:
        store = None

    if settings.dispatcher_ready and settings.task_api_key:
        dispatcher = GoogleCloudTasksDispatcher(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            queue=settings.cloud_tasks_queue,
            worker_url=settings.worker_url,
            task_api_key=settings.task_api_key,
            service_account_email=settings.task_service_account,
            deadline_seconds=settings.task_deadline_seconds,
        )
    elif settings.local_mode:
        dispatcher = RecordingDispatcher()
    else:
        dispatcher = None

    processor = None
    gemini_key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
    apify_token = str(os.getenv("APIFY_TOKEN", "") or "").strip()
    if gemini_key and apify_token:
        processor = TaggyPostProcessor(gemini_key, apify_token)
    return Runtime(settings, store, dispatcher, processor)


def create_app(
    *,
    settings: Optional[CloudBackendSettings] = None,
    store=None,
    dispatcher=None,
    processor=None,
) -> FastAPI:
    settings = settings or CloudBackendSettings.from_env()
    runtime = _build_runtime(settings)
    if store is not None:
        runtime.store = store
    if dispatcher is not None:
        runtime.dispatcher = dispatcher
    if processor is not None:
        runtime.processor = processor

    app = FastAPI(
        title="Taggy Job Backend",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = runtime

    def require_runtime() -> Runtime:
        if runtime.store is None or runtime.dispatcher is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cloud job storage or dispatch is not configured.",
            )
        return runtime

    def require_submission_runtime() -> Runtime:
        active = require_runtime()
        if active.processor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tagging providers are not configured.",
            )
        return active

    def require_backend_key(actual: str) -> None:
        if settings.local_mode and not settings.backend_api_key:
            return
        if not _constant_time_match(actual, settings.backend_api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def require_task_key(actual: str) -> None:
        if settings.local_mode and not settings.task_api_key:
            return
        if not _constant_time_match(actual, settings.task_api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.get("/healthz")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "ready": bool(runtime.store and runtime.dispatcher and runtime.processor),
            "storage": "configured" if runtime.store else "missing",
            "dispatcher": "configured" if runtime.dispatcher else "missing",
            "providers": "configured" if runtime.processor else "missing",
        }

    @app.post("/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: CreateJobRequest,
        x_taggy_backend_key: str = Header(default="", alias="X-Taggy-Backend-Key"),
    ) -> Dict[str, Any]:
        require_backend_key(x_taggy_backend_key)
        active = require_submission_runtime()
        try:
            job_id = validate_id(request.job_id)
            recovery_id = validate_id(request.recovery_id, "recovery ID")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not request.posts:
            raise HTTPException(status_code=422, detail="At least one post is required.")
        if request.model not in SUPPORTED_GEMINI_MODELS:
            raise HTTPException(status_code=422, detail="The selected model is not supported.")
        if len(request.posts) > settings.max_posts_per_job:
            raise HTTPException(
                status_code=422,
                detail=f"This beta accepts at most {settings.max_posts_per_job} posts per cloud job.",
            )
        sanitized_posts = [sanitize_mapping(row) for row in request.posts]
        for row in sanitized_posts:
            link = str(row.get("Link") or row.get("link") or "").strip()
            if not is_supported_post_url(link):
                raise HTTPException(status_code=422, detail="Every row requires a supported post link.")
        try:
            active.store.create_job(
                job_id,
                recovery_id,
                request.model,
                sanitized_posts,
            )
        except JobConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        dispatch_next(active.store, active.dispatcher, job_id)
        return active.store.summary(job_id)

    @app.get("/v1/jobs/{job_id}")
    def job_status(
        job_id: str,
        x_taggy_backend_key: str = Header(default="", alias="X-Taggy-Backend-Key"),
    ) -> Dict[str, Any]:
        require_backend_key(x_taggy_backend_key)
        active = require_runtime()
        try:
            return active.store.summary(validate_id(job_id))
        except (ValueError, JobNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Job not found.") from exc

    @app.get("/v1/jobs/{job_id}/results")
    def job_results(
        job_id: str,
        x_taggy_backend_key: str = Header(default="", alias="X-Taggy-Backend-Key"),
    ) -> Dict[str, Any]:
        require_backend_key(x_taggy_backend_key)
        active = require_runtime()
        try:
            validated = validate_id(job_id)
            summary = active.store.summary(validated)
            results = active.store.results(validated)
        except (ValueError, JobNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Job not found.") from exc
        return {"job": summary, "results": results}

    @app.post("/v1/jobs/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED)
    def resume_job(
        job_id: str,
        x_taggy_backend_key: str = Header(default="", alias="X-Taggy-Backend-Key"),
    ) -> Dict[str, Any]:
        require_backend_key(x_taggy_backend_key)
        active = require_submission_runtime()
        try:
            validated = validate_id(job_id)
            active.store.resume_job(validated)
            dispatch_next(active.store, active.dispatcher, validated)
            return active.store.summary(validated)
        except (ValueError, JobNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Job not found.") from exc

    @app.post("/internal/v1/tasks/tag-post")
    def tag_post(
        request: TaskRequest,
        x_taggy_task_key: str = Header(default="", alias="X-Taggy-Task-Key"),
    ) -> Dict[str, Any]:
        require_task_key(x_taggy_task_key)
        active = require_runtime()
        if active.processor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tagging providers are not configured.",
            )
        try:
            job_id = validate_id(request.job_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        worker_id = uuid.uuid4().hex
        try:
            claim = active.store.claim_post(
                job_id,
                int(request.position),
                worker_id,
                settings.post_lease_seconds,
            )
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Job post not found.") from exc

        claim_state = str(claim.get("state") or "")
        if claim_state == "completed":
            try:
                dispatch_next(active.store, active.dispatcher, job_id)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="The next task could not be dispatched yet.",
                ) from exc
            return {"status": "already_completed"}
        if claim_state == "busy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The post is still being processed.",
            )
        if claim_state == "failed":
            return {"status": "needs_attention"}
        if claim_state == "missing":
            raise HTTPException(status_code=404, detail="Job post not found.")
        if claim_state != "claimed" or not isinstance(claim.get("input"), dict):
            raise HTTPException(status_code=409, detail="Post could not be claimed.")

        try:
            result = sanitize_mapping(
                active.processor.process(
                    claim["input"], str(claim.get("model") or "")
                )
            )
        except Exception as exc:
            error_code = safe_processing_error_code(exc)
            retryable = (
                error_is_retryable(error_code)
                and int(claim.get("attempt_count") or 1)
                < settings.max_post_attempts
            )
            try:
                active.store.fail_post(
                    job_id,
                    int(request.position),
                    worker_id,
                    error_code,
                    retryable=retryable,
                )
            except Exception as storage_exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="The temporary failure could not be saved yet.",
                ) from storage_exc
            if retryable:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Temporary provider failure.",
                ) from exc
            return {"status": "needs_attention", "code": error_code}

        try:
            completed = active.store.complete_post(
                job_id,
                int(request.position),
                worker_id,
                result,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The completed post could not be saved yet.",
            ) from exc
        if not completed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The post lease changed before completion was saved.",
            )
        try:
            dispatch_next(active.store, active.dispatcher, job_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The next task could not be dispatched yet.",
            ) from exc
        return {"status": "completed", "position": int(request.position)}

    return app


app = create_app()
