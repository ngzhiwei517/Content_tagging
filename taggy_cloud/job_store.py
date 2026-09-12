"""Durable job state for independently scalable Taggy workers.

The production implementation uses Supabase's REST/RPC interface.  A small
in-memory implementation keeps API and orchestration tests deterministic.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests


SAFE_ID = re.compile(r"^[a-f0-9]{32}$")
TRANSIENT_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
DEFAULT_RETRY_DELAYS = (0.5, 1.0, 2.0)


class JobNotFoundError(LookupError):
    """Raised when a requested cloud job does not exist."""


class JobConflictError(RuntimeError):
    """Raised when an existing job ID is reused with different inputs."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_id(value: str, label: str = "job ID") -> str:
    candidate = str(value or "").strip().lower()
    if not SAFE_ID.fullmatch(candidate):
        raise ValueError(f"Invalid {label}.")
    return candidate


def request_fingerprint(
    recovery_id: str,
    model: str,
    posts: Sequence[Dict[str, Any]],
) -> str:
    canonical = json.dumps(
        {
            "recovery_id": recovery_id,
            "model": str(model or "").strip(),
            "posts": list(posts),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _response_has_sqlstate_57014(response) -> bool:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        values = (
            payload.get("code"),
            payload.get("sqlstate"),
            payload.get("message"),
            payload.get("details"),
        )
        if any("57014" in str(value or "") for value in values):
            return True
    return "57014" in str(getattr(response, "text", "") or "")


def _rpc_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    if isinstance(payload, list) and payload:
        payload = payload[0]
        if isinstance(payload, dict) and len(payload) == 1:
            nested = next(iter(payload.values()))
            if isinstance(nested, (dict, str)):
                return _rpc_payload(nested)
    if not isinstance(payload, dict):
        raise RuntimeError("Cloud job storage returned an invalid response.")
    return payload


def summarize_job(job: Dict[str, Any], posts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(posts)
    counts = {
        "pending": 0,
        "running": 0,
        "retryable": 0,
        "failed": 0,
        "completed": 0,
    }
    for row in rows:
        status = str(row.get("status") or "pending").casefold()
        if status in counts:
            counts[status] += 1
        else:
            counts["failed"] += 1

    total = int(job.get("total_posts") or len(rows))
    if total and counts["completed"] >= total:
        state = "completed"
    elif counts["running"]:
        state = "running"
    elif counts["failed"]:
        state = "needs_attention"
    elif counts["retryable"]:
        state = "retrying"
    elif counts["pending"]:
        state = "queued"
    else:
        state = str(job.get("status") or "queued")

    return {
        "job_id": job.get("job_id", ""),
        "recovery_id": job.get("recovery_id", ""),
        "status": state,
        "model": job.get("model", ""),
        "total_posts": total,
        "completed_posts": counts["completed"],
        "running_posts": counts["running"],
        "pending_posts": counts["pending"],
        "retryable_posts": counts["retryable"],
        "failed_posts": counts["failed"],
        "dispatch_generation": int(job.get("dispatch_generation") or 0),
        "created_at": job.get("created_at", ""),
        "updated_at": job.get("updated_at", ""),
    }


class InMemoryCloudJobStore:
    """Thread-safe test/local store implementing the production contract."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._posts: Dict[str, Dict[int, Dict[str, Any]]] = {}

    def create_job(
        self,
        job_id: str,
        recovery_id: str,
        model: str,
        posts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        job_id = validate_id(job_id)
        recovery_id = validate_id(recovery_id, "recovery ID")
        normalized_posts = [copy.deepcopy(dict(row)) for row in posts]
        now = utc_now()
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing:
                existing_inputs = [
                    self._posts[job_id][position]["input_payload"]
                    for position in sorted(self._posts[job_id])
                ]
                if (
                    existing.get("recovery_id") != recovery_id
                    or existing.get("model") != model
                    or existing_inputs != normalized_posts
                ):
                    raise JobConflictError("Job ID already belongs to another request.")
                return copy.deepcopy(existing)

            job = {
                "job_id": job_id,
                "recovery_id": recovery_id,
                "model": str(model or "").strip(),
                "request_hash": request_fingerprint(
                    recovery_id, model, normalized_posts
                ),
                "status": "queued",
                "total_posts": len(normalized_posts),
                "dispatch_generation": 0,
                "created_at": now,
                "updated_at": now,
            }
            self._jobs[job_id] = job
            self._posts[job_id] = {
                position: {
                    "job_id": job_id,
                    "position": position,
                    "status": "pending",
                    "input_payload": payload,
                    "result_payload": None,
                    "attempt_count": 0,
                    "worker_id": "",
                    "lease_until_epoch": 0.0,
                    "error_code": "",
                    "updated_at": now,
                }
                for position, payload in enumerate(normalized_posts)
            }
            return copy.deepcopy(job)

    def get_job(self, job_id: str) -> Dict[str, Any]:
        job_id = validate_id(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise JobNotFoundError(job_id)
            return copy.deepcopy(job)

    def list_posts(self, job_id: str) -> List[Dict[str, Any]]:
        job_id = validate_id(job_id)
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)
            return [
                copy.deepcopy(self._posts[job_id][position])
                for position in sorted(self._posts[job_id])
            ]

    def summary(self, job_id: str) -> Dict[str, Any]:
        return summarize_job(self.get_job(job_id), self.list_posts(job_id))

    def next_pending_position(self, job_id: str) -> Optional[int]:
        for row in self.list_posts(job_id):
            if row.get("status") == "pending":
                return int(row["position"])
        return None

    def claim_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        lease_seconds: int,
    ) -> Dict[str, Any]:
        job_id = validate_id(job_id)
        worker_id = validate_id(worker_id, "worker ID")
        with self._lock:
            if job_id not in self._jobs or position not in self._posts[job_id]:
                raise JobNotFoundError(job_id)
            row = self._posts[job_id][position]
            now_epoch = time.time()
            if row.get("status") == "completed":
                return {"state": "completed", "result": copy.deepcopy(row["result_payload"])}
            active_lease = (
                row.get("status") == "running"
                and float(row.get("lease_until_epoch") or 0) > now_epoch
                and row.get("worker_id") != worker_id
            )
            if active_lease:
                return {"state": "busy"}
            if row.get("status") == "failed":
                return {"state": "failed"}
            row.update(
                {
                    "status": "running",
                    "worker_id": worker_id,
                    "lease_until_epoch": now_epoch + max(120, int(lease_seconds)),
                    "attempt_count": int(row.get("attempt_count") or 0) + 1,
                    "error_code": "",
                    "updated_at": utc_now(),
                }
            )
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["updated_at"] = utc_now()
            return {
                "state": "claimed",
                "input": copy.deepcopy(row["input_payload"]),
                "model": self._jobs[job_id]["model"],
                "attempt_count": int(row["attempt_count"]),
            }

    def complete_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        result: Dict[str, Any],
    ) -> bool:
        job_id = validate_id(job_id)
        worker_id = validate_id(worker_id, "worker ID")
        with self._lock:
            row = self._posts.get(job_id, {}).get(position)
            if not row:
                raise JobNotFoundError(job_id)
            if row.get("status") == "completed":
                return True
            if row.get("worker_id") != worker_id:
                return False
            row.update(
                {
                    "status": "completed",
                    "result_payload": copy.deepcopy(result),
                    "worker_id": "",
                    "lease_until_epoch": 0.0,
                    "error_code": "",
                    "updated_at": utc_now(),
                }
            )
            summary = summarize_job(self._jobs[job_id], self._posts[job_id].values())
            self._jobs[job_id]["status"] = summary["status"]
            self._jobs[job_id]["updated_at"] = utc_now()
            return True

    def fail_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        error_code: str,
        *,
        retryable: bool,
    ) -> None:
        job_id = validate_id(job_id)
        worker_id = validate_id(worker_id, "worker ID")
        with self._lock:
            row = self._posts.get(job_id, {}).get(position)
            if not row:
                raise JobNotFoundError(job_id)
            if row.get("status") == "completed":
                return
            if row.get("worker_id") not in {"", worker_id}:
                return
            row.update(
                {
                    "status": "retryable" if retryable else "failed",
                    "worker_id": "",
                    "lease_until_epoch": 0.0,
                    "error_code": str(error_code or "PROCESSING_FAILED")[:80],
                    "updated_at": utc_now(),
                }
            )
            self._jobs[job_id]["status"] = (
                "queued" if retryable else "needs_attention"
            )
            self._jobs[job_id]["updated_at"] = utc_now()

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        job_id = validate_id(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise JobNotFoundError(job_id)
            now_epoch = time.time()
            for row in self._posts[job_id].values():
                expired = (
                    row.get("status") == "running"
                    and float(row.get("lease_until_epoch") or 0) <= now_epoch
                )
                if row.get("status") in {"retryable", "failed"} or expired:
                    row.update(
                        {
                            "status": "pending",
                            "worker_id": "",
                            "lease_until_epoch": 0.0,
                            "error_code": "",
                            "updated_at": utc_now(),
                        }
                    )
            job["dispatch_generation"] = int(job.get("dispatch_generation") or 0) + 1
            job["status"] = "queued"
            job["updated_at"] = utc_now()
            return copy.deepcopy(job)

    def results(self, job_id: str) -> List[Dict[str, Any]]:
        rows = self.list_posts(job_id)
        return [
            {
                "position": int(row["position"]),
                "result": copy.deepcopy(row["result_payload"]),
            }
            for row in rows
            if row.get("status") == "completed"
            and isinstance(row.get("result_payload"), dict)
        ]


class SupabaseCloudJobStore:
    """Supabase-backed job store using transactional SQL RPC functions."""

    def __init__(
        self,
        url: str,
        key: str,
        *,
        timeout_seconds: float = 20.0,
        session: Optional[requests.Session] = None,
        retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
        sleep=time.sleep,
    ) -> None:
        self.url = re.sub(r"/rest/v1$", "", str(url or "").strip().rstrip("/"), flags=re.I)
        self.key = str(key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self.session = session or requests.Session()
        self.retry_delays = tuple(max(0.0, float(delay)) for delay in retry_delays)
        self.sleep = sleep
        if not self.url.startswith(("https://", "http://")) or not self.key:
            raise ValueError("Supabase URL and server-side key are required.")

    def _headers(self, *, upsert: bool = False) -> Dict[str, str]:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if not self.key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.key}"
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        return headers

    def _request(self, method: str, url: str, **kwargs):
        operation = getattr(self.session, method)
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                response = operation(
                    url,
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
                retryable = (
                    getattr(response, "status_code", None) in TRANSIENT_HTTP_STATUS
                    or _response_has_sqlstate_57014(response)
                )
                if retryable and attempt < attempts - 1:
                    self.sleep(self.retry_delays[attempt])
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError):
                if attempt >= attempts - 1:
                    raise
                self.sleep(self.retry_delays[attempt])
        raise RuntimeError("Cloud job storage did not return a response.")

    def _rpc(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request(
            "post",
            f"{self.url}/rest/v1/rpc/{name}",
            headers=self._headers(),
            json=payload,
        )
        return _rpc_payload(response.json())

    def create_job(
        self,
        job_id: str,
        recovery_id: str,
        model: str,
        posts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        validated_job_id = validate_id(job_id)
        validated_recovery_id = validate_id(recovery_id, "recovery ID")
        try:
            return self._rpc(
                "taggy_cloud_create_job",
                {
                    "p_job_id": validated_job_id,
                    "p_recovery_id": validated_recovery_id,
                    "p_request_hash": request_fingerprint(
                        validated_recovery_id, model, posts
                    ),
                    "p_model": str(model or "").strip(),
                    "p_posts": list(posts),
                },
            )
        except requests.HTTPError as exc:
            response_text = str(
                getattr(getattr(exc, "response", None), "text", "") or ""
            )
            if "TAGGY_JOB_CONFLICT" in response_text:
                raise JobConflictError(
                    "Job ID already belongs to another request."
                ) from exc
            raise

    def get_job(self, job_id: str) -> Dict[str, Any]:
        job_id = validate_id(job_id)
        response = self._request(
            "get",
            f"{self.url}/rest/v1/taggy_cloud_jobs",
            headers=self._headers(),
            params={"job_id": f"eq.{job_id}", "select": "*", "limit": "1"},
        )
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise JobNotFoundError(job_id)
        return dict(rows[0])

    def list_posts(self, job_id: str) -> List[Dict[str, Any]]:
        job_id = validate_id(job_id)
        response = self._request(
            "get",
            f"{self.url}/rest/v1/taggy_cloud_job_posts",
            headers=self._headers(),
            params={
                "job_id": f"eq.{job_id}",
                "select": "position,status,input_payload,result_payload,attempt_count,error_code,updated_at",
                "order": "position.asc",
            },
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError("Cloud job storage returned invalid post rows.")
        return [dict(row) for row in rows if isinstance(row, dict)]

    def summary(self, job_id: str) -> Dict[str, Any]:
        return summarize_job(self.get_job(job_id), self.list_posts(job_id))

    def next_pending_position(self, job_id: str) -> Optional[int]:
        job_id = validate_id(job_id)
        response = self._request(
            "get",
            f"{self.url}/rest/v1/taggy_cloud_job_posts",
            headers=self._headers(),
            params={
                "job_id": f"eq.{job_id}",
                "status": "eq.pending",
                "select": "position",
                "order": "position.asc",
                "limit": "1",
            },
        )
        rows = response.json()
        return int(rows[0]["position"]) if isinstance(rows, list) and rows else None

    def claim_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        lease_seconds: int,
    ) -> Dict[str, Any]:
        return self._rpc(
            "taggy_cloud_claim_post",
            {
                "p_job_id": validate_id(job_id),
                "p_position": int(position),
                "p_worker_id": validate_id(worker_id, "worker ID"),
                "p_lease_seconds": max(120, min(3600, int(lease_seconds))),
            },
        )

    def complete_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        result: Dict[str, Any],
    ) -> bool:
        payload = self._rpc(
            "taggy_cloud_complete_post",
            {
                "p_job_id": validate_id(job_id),
                "p_position": int(position),
                "p_worker_id": validate_id(worker_id, "worker ID"),
                "p_result": result,
            },
        )
        return bool(payload.get("completed"))

    def fail_post(
        self,
        job_id: str,
        position: int,
        worker_id: str,
        error_code: str,
        *,
        retryable: bool,
    ) -> None:
        self._rpc(
            "taggy_cloud_fail_post",
            {
                "p_job_id": validate_id(job_id),
                "p_position": int(position),
                "p_worker_id": validate_id(worker_id, "worker ID"),
                "p_error_code": str(error_code or "PROCESSING_FAILED")[:80],
                "p_retryable": bool(retryable),
            },
        )

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        return self._rpc(
            "taggy_cloud_resume_job",
            {"p_job_id": validate_id(job_id)},
        )

    def results(self, job_id: str) -> List[Dict[str, Any]]:
        return [
            {"position": int(row["position"]), "result": row["result_payload"]}
            for row in self.list_posts(job_id)
            if row.get("status") == "completed"
            and isinstance(row.get("result_payload"), dict)
        ]
