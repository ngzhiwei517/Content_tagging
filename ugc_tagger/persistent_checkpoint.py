"""Optional durable persistence for secret-free checkpoint objects."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

import requests


_SAFE_RECOVERY_ID = re.compile(r"^[a-f0-9]{32}$")
_SAFE_OBJECT_KEY = re.compile(r"^[a-zA-Z0-9_./-]{1,240}$")
_SAFE_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PersistentCheckpointConfig:
    gcs_bucket: str = ""
    gcs_project: str = ""
    gcs_prefix: str = "taggy-checkpoints"
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    table: str = "batch_checkpoint_objects"
    # Recovery payloads can contain a few hundred sanitized post rows. Five
    # seconds was too aggressive for a cold Supabase project or a larger
    # batch, so allow enough time for one server-side upsert and readback.
    timeout_seconds: float = 20.0


_TRANSIENT_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
_DEFAULT_RETRY_DELAYS = (0.5, 1.0, 2.0)


def _sqlstate(exc: Exception) -> str:
    """Return a Postgres SQLSTATE without exposing the original statement."""
    for value in (
        getattr(exc, "sqlstate", ""),
        getattr(exc, "pgcode", ""),
        getattr(getattr(exc, "diag", None), "sqlstate", ""),
    ):
        candidate = str(value or "").strip()
        if candidate:
            return candidate
    return ""


def _response_has_sqlstate_57014(response) -> bool:
    """Recognise PostgREST query-cancel errors even when HTTP status is 4xx."""
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


def _queue_payload(payload: Any) -> Dict[str, Any]:
    """Normalize the JSON shape returned by PostgREST or psycopg."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    if isinstance(payload, list) and payload:
        payload = payload[0]
        if isinstance(payload, dict) and len(payload) == 1:
            only_value = next(iter(payload.values()))
            if isinstance(only_value, (dict, str)):
                return _queue_payload(only_value)
    if not isinstance(payload, dict):
        raise RuntimeError("Tagging worker queue returned an invalid response.")
    return payload


def checkpoint_error_code(exc: Exception) -> str:
    """Return a safe diagnostic code without exposing request data or keys."""
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "network_failed"
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            return "auth_failed"
        if status_code == 403:
            return "permission_denied"
        if status_code == 404:
            return "table_missing"
        if status_code == 429:
            return "rate_limited"
        if isinstance(status_code, int) and status_code >= 500:
            return "service_unavailable"
        return "http_failed"
    status_code = getattr(exc, "code", None)
    if callable(status_code):
        try:
            status_code = status_code()
        except TypeError:
            status_code = None
    status_code = getattr(status_code, "value", status_code)
    if not isinstance(status_code, int):
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 401:
        return "auth_failed"
    if status_code == 403:
        return "permission_denied"
    if status_code == 404:
        return "object_missing"
    if status_code == 429:
        return "rate_limited"
    if isinstance(status_code, int) and status_code >= 500:
        return "service_unavailable"
    error_name = type(exc).__name__.lower()
    if "timeout" in error_name or "deadline" in error_name:
        return "timeout"
    if "connection" in error_name:
        return "network_failed"
    return "save_failed"


def _validate_identifier(value: str, default: str) -> str:
    candidate = str(value or default).strip()
    if not _SAFE_SQL_IDENTIFIER.fullmatch(candidate):
        raise ValueError("Checkpoint table must be a simple SQL identifier.")
    return candidate


def _validate_object(recovery_id: str, object_key: str) -> tuple[str, str]:
    recovery_id = str(recovery_id or "").strip().lower()
    object_key = str(object_key or "").strip().replace("\\", "/")
    if not _SAFE_RECOVERY_ID.fullmatch(recovery_id):
        raise ValueError("Invalid recovery ID.")
    if not _SAFE_OBJECT_KEY.fullmatch(object_key) or ".." in object_key.split("/"):
        raise ValueError("Invalid checkpoint object key.")
    return recovery_id, object_key


def _validate_storage_prefix(value: str) -> str:
    prefix = str(value or "").strip().strip("/").replace("\\", "/")
    if not prefix:
        return ""
    if not _SAFE_OBJECT_KEY.fullmatch(prefix) or ".." in prefix.split("/"):
        raise ValueError("Invalid checkpoint storage prefix.")
    return prefix


class GoogleCloudStorageCheckpointBackend:
    """Store each checkpoint object as private JSON in one Cloud Storage bucket."""

    def __init__(
        self,
        bucket_name: str,
        *,
        project: str = "",
        prefix: str = "taggy-checkpoints",
        timeout_seconds: float = 20.0,
        client=None,
    ) -> None:
        bucket_name = str(bucket_name or "").strip()
        if bucket_name.lower().startswith("gs://"):
            bucket_name = bucket_name[5:]
        bucket_name = bucket_name.strip("/")
        if not bucket_name or "/" in bucket_name:
            raise ValueError("A Cloud Storage bucket name is required.")
        self.bucket_name = bucket_name
        self.project = str(project or "").strip()
        self.prefix = _validate_storage_prefix(prefix)
        self.timeout_seconds = float(timeout_seconds)
        if client is None:
            try:
                from google.cloud import storage
            except ImportError as exc:  # pragma: no cover - deployment dependency
                raise RuntimeError(
                    "Cloud Storage checkpointing requires google-cloud-storage."
                ) from exc
            client = storage.Client(project=self.project or None)
        self.client = client
        self.bucket = client.bucket(self.bucket_name)

    def _object_name(self, recovery_id: str, object_key: str) -> tuple[str, str]:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        base = f"{self.prefix}/" if self.prefix else ""
        return f"{base}{recovery_id}/{object_key}", object_key

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        return checkpoint_error_code(exc) == "object_missing"

    def save(self, recovery_id: str, object_key: str, payload: Any) -> None:
        object_name, _ = self._object_name(recovery_id, object_key)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        self.bucket.blob(object_name).upload_from_string(
            serialized,
            content_type="application/json",
            timeout=self.timeout_seconds,
        )

    def load(self, recovery_id: str, object_key: str) -> Any:
        object_name, _ = self._object_name(recovery_id, object_key)
        try:
            data = self.bucket.blob(object_name).download_as_bytes(
                timeout=self.timeout_seconds
            )
        except Exception as exc:
            if self._is_not_found(exc):
                return None
            raise
        payload = json.loads(data.decode("utf-8"))
        return payload if isinstance(payload, (dict, list)) else None

    def list_prefix(self, recovery_id: str, prefix: str) -> Dict[str, Any]:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        root = f"{self.prefix}/" if self.prefix else ""
        recovery_root = f"{root}{recovery_id}/"
        rows: Dict[str, Any] = {}
        for blob in self.client.list_blobs(
            self.bucket_name,
            prefix=f"{recovery_root}{prefix}",
            timeout=self.timeout_seconds,
        ):
            name = str(getattr(blob, "name", ""))
            if not name.startswith(recovery_root):
                continue
            object_key = name[len(recovery_root):]
            data = blob.download_as_bytes(timeout=self.timeout_seconds)
            payload = json.loads(data.decode("utf-8"))
            if isinstance(payload, (dict, list)):
                rows[object_key] = payload
        return rows

    def delete(self, recovery_id: str, object_key: str) -> None:
        object_name, _ = self._object_name(recovery_id, object_key)
        try:
            self.bucket.blob(object_name).delete(timeout=self.timeout_seconds)
        except Exception as exc:
            if not self._is_not_found(exc):
                raise

    def delete_prefix(self, recovery_id: str, prefix: str) -> None:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        root = f"{self.prefix}/" if self.prefix else ""
        recovery_root = f"{root}{recovery_id}/"
        for blob in self.client.list_blobs(
            self.bucket_name,
            prefix=f"{recovery_root}{prefix}",
            timeout=self.timeout_seconds,
        ):
            blob.delete(timeout=self.timeout_seconds)


class SupabaseCheckpointBackend:
    def __init__(
        self,
        url: str,
        key: str,
        *,
        table: str = "batch_checkpoint_objects",
        timeout_seconds: float = 20.0,
        session: Optional[requests.Session] = None,
        retry_delays: Sequence[float] = _DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        raw_url = str(url or "").strip().rstrip("/")
        # Supabase displays both the project URL and a Data API URL ending in
        # ``/rest/v1/``.  Accept either form.  Without this normalization the
        # endpoint became ``.../rest/v1/rest/v1/<table>`` and remote writes
        # failed while the same-process local fallback appeared to work.
        self.url = re.sub(r"/rest/v1$", "", raw_url, flags=re.IGNORECASE)
        self.key = str(key or "").strip()
        self.table = _validate_identifier(table, "batch_checkpoint_objects")
        self.timeout_seconds = float(timeout_seconds)
        # ``requests.Session`` is not guaranteed to be thread-safe. Keep an
        # injected test session as-is, but give each Streamlit/background
        # thread its own connection pool in production.
        self.session = session
        self._thread_local = threading.local()
        self.retry_delays = tuple(max(0.0, float(value)) for value in retry_delays)
        self.sleep = sleep
        if not self.url.startswith(("https://", "http://")) or not self.key:
            raise ValueError("Supabase URL and server-side key are required.")

    @property
    def endpoint(self) -> str:
        return f"{self.url}/rest/v1/{self.table}"

    def rpc_endpoint(self, function_name: str) -> str:
        function_name = _validate_identifier(function_name, function_name)
        return f"{self.url}/rest/v1/rpc/{function_name}"

    def _headers(self, *, upsert: bool = False) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
        }
        # Supabase's current sb_* keys are opaque API keys, not JWTs. Sending
        # one as a bearer token can make the Data API reject it as an invalid
        # JWT. Legacy service_role JWT keys still support bearer auth.
        if not self.key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.key}"
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        return headers

    def _request(self, method: str, *args, **kwargs):
        """Send an idempotent request with bounded exponential backoff."""
        request_session = self.session
        if request_session is None:
            request_session = getattr(self._thread_local, "session", None)
            if request_session is None:
                request_session = requests.Session()
                self._thread_local.session = request_session
        operation = getattr(request_session, method)
        last_error = None
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                response = operation(*args, timeout=self.timeout_seconds, **kwargs)
                status_code = getattr(response, "status_code", None)
                retryable_response = (
                    status_code in _TRANSIENT_HTTP_STATUS
                    or _response_has_sqlstate_57014(response)
                )
                if retryable_response and attempt < attempts - 1:
                    self.sleep(self.retry_delays[attempt])
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    self.sleep(self.retry_delays[attempt])
                    continue
                raise
        if last_error is not None:  # pragma: no cover - defensive fallback
            raise last_error
        raise RuntimeError("Checkpoint request did not return a response.")

    def save(self, recovery_id: str, object_key: str, payload: Any) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        self._request(
            "post",
            self.endpoint,
            params={"on_conflict": "recovery_id,object_key"},
            headers=self._headers(upsert=True),
            json={
                "recovery_id": recovery_id,
                "object_key": object_key,
                "payload": payload,
            },
        )

    def load(self, recovery_id: str, object_key: str) -> Any:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        response = self._request(
            "get",
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"eq.{object_key}",
                "select": "payload",
                "limit": "1",
            },
            headers=self._headers(),
        )
        rows = response.json()
        payload = rows[0].get("payload") if isinstance(rows, list) and rows else None
        return payload if isinstance(payload, (dict, list)) else None

    def list_prefix(self, recovery_id: str, prefix: str) -> Dict[str, Any]:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        response = self._request(
            "get",
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"like.{prefix}%",
                "select": "object_key,payload",
            },
            headers=self._headers(),
        )
        rows = response.json()
        if not isinstance(rows, list):
            return {}
        return {
            row["object_key"]: row["payload"]
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("object_key"), str)
            and isinstance(row.get("payload"), (dict, list))
        }

    def delete(self, recovery_id: str, object_key: str) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        self._request(
            "delete",
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"eq.{object_key}",
            },
            headers=self._headers(),
        )

    def delete_prefix(self, recovery_id: str, prefix: str) -> None:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        self._request(
            "delete",
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"like.{prefix}%",
            },
            headers=self._headers(),
        )

    def claim_tagging_worker(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: int = 7200,
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        recovery_id, _ = _validate_object(recovery_id, "runtime.json")
        job_id, _ = _validate_object(job_id, "runtime.json")
        owner_id, _ = _validate_object(owner_id, "runtime.json")
        response = self._request(
            "post",
            self.rpc_endpoint("tagging_pool_claim"),
            headers=self._headers(),
            json={
                "p_recovery_id": recovery_id,
                "p_job_id": job_id,
                "p_owner_id": owner_id,
                "p_lease_seconds": max(60, int(lease_seconds)),
                "p_max_workers": max(1, min(16, int(max_workers))),
            },
        )
        return _queue_payload(response.json())

    def release_tagging_worker(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
    ) -> bool:
        recovery_id, _ = _validate_object(recovery_id, "runtime.json")
        job_id, _ = _validate_object(job_id, "runtime.json")
        owner_id, _ = _validate_object(owner_id, "runtime.json")
        response = self._request(
            "post",
            self.rpc_endpoint("tagging_pool_release"),
            headers=self._headers(),
            json={
                "p_recovery_id": recovery_id,
                "p_job_id": job_id,
                "p_owner_id": owner_id,
            },
        )
        payload = response.json()
        if isinstance(payload, list) and payload:
            payload = payload[0]
            if isinstance(payload, dict) and len(payload) == 1:
                payload = next(iter(payload.values()))
        return bool(payload)


class PostgresCheckpointBackend:
    def __init__(
        self,
        database_url: str,
        *,
        table: str = "batch_checkpoint_objects",
        retry_delays: Sequence[float] = _DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        self.table = _validate_identifier(table, "batch_checkpoint_objects")
        self.retry_delays = tuple(max(0.0, float(value)) for value in retry_delays)
        self.sleep = sleep
        if not self.database_url:
            raise ValueError("Postgres connection URL is required.")

    @staticmethod
    def _driver():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional deployment dependency
            raise RuntimeError("Postgres checkpointing requires psycopg.") from exc
        return psycopg

    def _run(self, operation):
        """Retry cancelled or disconnected Postgres work from a fresh connection."""
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                return operation()
            except Exception as exc:
                sqlstate = _sqlstate(exc)
                retryable = sqlstate == "57014" or sqlstate.startswith("08")
                if not retryable or attempt >= attempts - 1:
                    raise
                self.sleep(self.retry_delays[attempt])

    def save(self, recovery_id: str, object_key: str, payload: Any) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        statement = (
            f"INSERT INTO {self.table} (recovery_id, object_key, payload, updated_at) "
            "VALUES (%s, %s, %s::jsonb, NOW()) "
            "ON CONFLICT (recovery_id, object_key) DO UPDATE "
            "SET payload = EXCLUDED.payload, updated_at = NOW()"
        )
        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, object_key, json.dumps(payload)))

        self._run(operation)

    def load(self, recovery_id: str, object_key: str) -> Any:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        statement = f"SELECT payload FROM {self.table} WHERE recovery_id = %s AND object_key = %s LIMIT 1"
        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, object_key))
                    return cursor.fetchone()

        row = self._run(operation)
        if not row:
            return None
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return payload if isinstance(payload, (dict, list)) else None

    def list_prefix(self, recovery_id: str, prefix: str) -> Dict[str, Any]:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        statement = f"SELECT object_key, payload FROM {self.table} WHERE recovery_id = %s AND object_key LIKE %s"
        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, f"{prefix}%"))
                    return cursor.fetchall()

        rows = self._run(operation)
        output = {}
        for key, payload in rows:
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(key, str) and isinstance(payload, (dict, list)):
                output[key] = payload
        return output

    def delete(self, recovery_id: str, object_key: str) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        statement = f"DELETE FROM {self.table} WHERE recovery_id = %s AND object_key = %s"
        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, object_key))

        self._run(operation)

    def delete_prefix(self, recovery_id: str, prefix: str) -> None:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        statement = f"DELETE FROM {self.table} WHERE recovery_id = %s AND object_key LIKE %s"
        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, f"{prefix}%"))

        self._run(operation)

    def claim_tagging_worker(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: int = 7200,
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        recovery_id, _ = _validate_object(recovery_id, "runtime.json")
        job_id, _ = _validate_object(job_id, "runtime.json")
        owner_id, _ = _validate_object(owner_id, "runtime.json")
        statement = "SELECT public.tagging_pool_claim(%s, %s, %s, %s, %s)"

        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        statement,
                        (
                            recovery_id,
                            job_id,
                            owner_id,
                            max(60, int(lease_seconds)),
                            max(1, min(16, int(max_workers))),
                        ),
                    )
                    return cursor.fetchone()

        row = self._run(operation)
        return _queue_payload(row[0] if row else None)

    def release_tagging_worker(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
    ) -> bool:
        recovery_id, _ = _validate_object(recovery_id, "runtime.json")
        job_id, _ = _validate_object(job_id, "runtime.json")
        owner_id, _ = _validate_object(owner_id, "runtime.json")
        statement = "SELECT public.tagging_pool_release(%s, %s, %s)"

        def operation():
            with self._driver().connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, (recovery_id, job_id, owner_id))
                    return cursor.fetchone()

        row = self._run(operation)
        return bool(row and row[0])


class RecoveryCheckpointObjects:
    """Bind one backend to a validated recovery ID and optional key prefix."""

    def __init__(self, backend, recovery_id: str, *, prefix: str = "") -> None:
        recovery_id, _ = _validate_object(recovery_id, "runtime.json")
        self.backend = backend
        self.recovery_id = recovery_id
        self.prefix = str(prefix or "").strip("/")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def save(self, key: str, payload: Any) -> None:
        self.backend.save(self.recovery_id, self._key(key), payload)

    def load(self, key: str) -> Any:
        return self.backend.load(self.recovery_id, self._key(key))

    def list_prefix(self, prefix: str) -> Dict[str, Any]:
        full_prefix = self._key(prefix)
        rows = self.backend.list_prefix(self.recovery_id, full_prefix)
        strip_prefix = f"{self.prefix}/" if self.prefix else ""
        return {
            key[len(strip_prefix):] if key.startswith(strip_prefix) else key: payload
            for key, payload in rows.items()
        }

    def delete(self, key: str) -> None:
        self.backend.delete(self.recovery_id, self._key(key))

    def delete_prefix(self, prefix: str) -> None:
        self.backend.delete_prefix(self.recovery_id, self._key(prefix))


def create_persistent_checkpoint_backend(config: PersistentCheckpointConfig):
    if str(config.gcs_bucket or "").strip():
        return GoogleCloudStorageCheckpointBackend(
            config.gcs_bucket,
            project=config.gcs_project,
            prefix=config.gcs_prefix,
            timeout_seconds=config.timeout_seconds,
        )
    table = _validate_identifier(config.table, "batch_checkpoint_objects")
    if str(config.database_url or "").strip():
        return PostgresCheckpointBackend(config.database_url, table=table)
    if str(config.supabase_url or "").strip() and str(config.supabase_key or "").strip():
        return SupabaseCheckpointBackend(
            config.supabase_url,
            config.supabase_key,
            table=table,
            timeout_seconds=config.timeout_seconds,
        )
    return None
