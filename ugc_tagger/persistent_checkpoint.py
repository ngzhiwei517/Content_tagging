"""Optional Supabase/Postgres persistence for secret-free checkpoint objects."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


_SAFE_RECOVERY_ID = re.compile(r"^[a-f0-9]{32}$")
_SAFE_OBJECT_KEY = re.compile(r"^[a-zA-Z0-9_./-]{1,240}$")
_SAFE_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PersistentCheckpointConfig:
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    table: str = "batch_checkpoint_objects"
    timeout_seconds: float = 5.0


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


class SupabaseCheckpointBackend:
    def __init__(
        self,
        url: str,
        key: str,
        *,
        table: str = "batch_checkpoint_objects",
        timeout_seconds: float = 5.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.url = str(url or "").strip().rstrip("/")
        self.key = str(key or "").strip()
        self.table = _validate_identifier(table, "batch_checkpoint_objects")
        self.timeout_seconds = float(timeout_seconds)
        self.session = session or requests.Session()
        if not self.url.startswith(("https://", "http://")) or not self.key:
            raise ValueError("Supabase URL and server-side key are required.")

    @property
    def endpoint(self) -> str:
        return f"{self.url}/rest/v1/{self.table}"

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

    def save(self, recovery_id: str, object_key: str, payload: Any) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        response = self.session.post(
            self.endpoint,
            params={"on_conflict": "recovery_id,object_key"},
            headers=self._headers(upsert=True),
            json={
                "recovery_id": recovery_id,
                "object_key": object_key,
                "payload": payload,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def load(self, recovery_id: str, object_key: str) -> Any:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        response = self.session.get(
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"eq.{object_key}",
                "select": "payload",
                "limit": "1",
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        payload = rows[0].get("payload") if isinstance(rows, list) and rows else None
        return payload if isinstance(payload, (dict, list)) else None

    def list_prefix(self, recovery_id: str, prefix: str) -> Dict[str, Any]:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        response = self.session.get(
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"like.{prefix}%",
                "select": "object_key,payload",
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
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
        response = self.session.delete(
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"eq.{object_key}",
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def delete_prefix(self, recovery_id: str, prefix: str) -> None:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        response = self.session.delete(
            self.endpoint,
            params={
                "recovery_id": f"eq.{recovery_id}",
                "object_key": f"like.{prefix}%",
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


class PostgresCheckpointBackend:
    def __init__(self, database_url: str, *, table: str = "batch_checkpoint_objects") -> None:
        self.database_url = str(database_url or "").strip()
        self.table = _validate_identifier(table, "batch_checkpoint_objects")
        if not self.database_url:
            raise ValueError("Postgres connection URL is required.")

    @staticmethod
    def _driver():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional deployment dependency
            raise RuntimeError("Postgres checkpointing requires psycopg.") from exc
        return psycopg

    def save(self, recovery_id: str, object_key: str, payload: Any) -> None:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        statement = (
            f"INSERT INTO {self.table} (recovery_id, object_key, payload, updated_at) "
            "VALUES (%s, %s, %s::jsonb, NOW()) "
            "ON CONFLICT (recovery_id, object_key) DO UPDATE "
            "SET payload = EXCLUDED.payload, updated_at = NOW()"
        )
        with self._driver().connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (recovery_id, object_key, json.dumps(payload)))

    def load(self, recovery_id: str, object_key: str) -> Any:
        recovery_id, object_key = _validate_object(recovery_id, object_key)
        statement = f"SELECT payload FROM {self.table} WHERE recovery_id = %s AND object_key = %s LIMIT 1"
        with self._driver().connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (recovery_id, object_key))
                row = cursor.fetchone()
        if not row:
            return None
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return payload if isinstance(payload, (dict, list)) else None

    def list_prefix(self, recovery_id: str, prefix: str) -> Dict[str, Any]:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        statement = f"SELECT object_key, payload FROM {self.table} WHERE recovery_id = %s AND object_key LIKE %s"
        with self._driver().connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (recovery_id, f"{prefix}%"))
                rows = cursor.fetchall()
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
        with self._driver().connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (recovery_id, object_key))

    def delete_prefix(self, recovery_id: str, prefix: str) -> None:
        recovery_id, prefix = _validate_object(recovery_id, prefix)
        statement = f"DELETE FROM {self.table} WHERE recovery_id = %s AND object_key LIKE %s"
        with self._driver().connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (recovery_id, f"{prefix}%"))


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
