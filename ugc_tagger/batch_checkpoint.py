"""Durable, secret-free checkpoints for large tagging batches.

The Streamlit entry point processes one chunk per script execution.  This
module stores completed chunk outputs and the current chunk's scraped records
under ``.tmp`` so a rerun or reconnect can continue without starting the
entire batch again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd


CHECKPOINT_VERSION = 1
DEFAULT_CHUNK_SIZE = 50
DEFAULT_RETENTION_HOURS = 72
_SAFE_ID = re.compile(r"^[a-f0-9]{32}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_safe(value):
    """Return a JSON-compatible value without serialising credentials."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            key_normalized = re.sub(r"[^a-z0-9]+", "_", key_text.lower()).strip("_")
            if (
                "token" in key_normalized
                or "api_key" in key_normalized
                or key_normalized in {"authorization", "cookie", "cookies", "password", "secret"}
            ):
                continue
            cleaned[key_text] = _json_safe(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)


def dataframe_to_payload(df: pd.DataFrame) -> Dict:
    """Convert a DataFrame to a portable JSON payload without pickle."""
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    return json.loads(
        df.to_json(
            orient="split",
            date_format="iso",
            date_unit="ms",
            default_handler=str,
        )
    )


def dataframe_from_payload(payload) -> pd.DataFrame:
    """Restore a DataFrame payload and its original index where possible."""
    if not isinstance(payload, dict):
        return pd.DataFrame()
    columns = payload.get("columns", [])
    data = payload.get("data", [])
    if not isinstance(columns, list) or not isinstance(data, list):
        return pd.DataFrame()
    restored = pd.DataFrame(data, columns=columns)
    index = payload.get("index", [])
    if isinstance(index, list) and len(index) == len(restored):
        restored.index = index
    return restored


def input_fingerprint(df: pd.DataFrame, model: str) -> str:
    """Fingerprint ordered inputs so a checkpoint is never used for another run."""
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    columns = [
        column
        for column in ("Platform", "Source", "Link", "Market", "Track", "Date", "Creator")
        if column in df.columns
    ]
    payload = dataframe_to_payload(df.loc[:, columns].reset_index(drop=True))
    canonical = json.dumps(
        {"model": str(model), "input": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BatchCheckpointStore:
    """Atomic file-backed checkpoint store for one Streamlit deployment."""

    def __init__(
        self,
        root: Path,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        retention_hours: int = DEFAULT_RETENTION_HOURS,
    ) -> None:
        self.root = Path(root)
        self.chunk_size = max(1, int(chunk_size))
        self.retention_hours = max(1, int(retention_hours))

    def _job_id(self, runtime_id: str, fingerprint: str) -> str:
        seed = f"{runtime_id}:{fingerprint}:{self.chunk_size}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    def _validated_job_id(self, job_id: str) -> str:
        candidate = str(job_id or "").strip().lower()
        if not _SAFE_ID.fullmatch(candidate):
            raise ValueError("Invalid tagging checkpoint id.")
        return candidate

    def _job_dir(self, job_id: str) -> Path:
        return self.root / self._validated_job_id(job_id)

    def _manifest_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "manifest.json"

    def _chunk_path(self, job_id: str, chunk_index: int) -> Path:
        return self._job_dir(job_id) / f"chunk_{int(chunk_index):05d}.json"

    def _records_path(self, job_id: str, chunk_index: int) -> Path:
        return self._job_dir(job_id) / f"records_{int(chunk_index):05d}.json"

    @staticmethod
    def _atomic_write_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def cleanup_old_jobs(self) -> None:
        """Remove abandoned runtime data after the retention window."""
        if not self.root.exists():
            return
        cutoff = time.time() - (self.retention_hours * 60 * 60)
        for child in self.root.iterdir():
            if not child.is_dir() or not _SAFE_ID.fullmatch(child.name):
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child)
            except OSError:
                continue

    def prepare(
        self,
        runtime_id: str,
        selected: pd.DataFrame,
        *,
        model: str,
        comparison_run_id: str,
        comparison_started_utc: str,
    ) -> Dict:
        """Create a new job or reconcile an existing resumable job."""
        fingerprint = input_fingerprint(selected, model)
        job_id = self._job_id(runtime_id, fingerprint)
        existing = self.load_manifest(job_id)
        total_rows = len(selected)
        total_chunks = (total_rows + self.chunk_size - 1) // self.chunk_size

        if (
            existing
            and existing.get("fingerprint") == fingerprint
            and int(existing.get("total_rows", -1)) == total_rows
            and int(existing.get("chunk_size", -1)) == self.chunk_size
        ):
            return self.reconcile(existing)

        now = _utc_now()
        manifest = {
            "version": CHECKPOINT_VERSION,
            "job_id": job_id,
            "fingerprint": fingerprint,
            "status": "running",
            "model": str(model),
            "total_rows": total_rows,
            "chunk_size": self.chunk_size,
            "total_chunks": total_chunks,
            "completed_chunks": [],
            "completed_rows": 0,
            "comparison_run_id": str(comparison_run_id),
            "comparison_started_utc": str(comparison_started_utc),
            "elapsed_seconds": 0.0,
            "last_error": "",
            "created_at": now,
            "updated_at": now,
        }
        self._atomic_write_json(self._manifest_path(job_id), manifest)
        return manifest

    def find(
        self,
        runtime_id: str,
        selected: pd.DataFrame,
        *,
        model: str,
    ) -> Optional[Dict]:
        """Return the matching job without creating one."""
        fingerprint = input_fingerprint(selected, model)
        job_id = self._job_id(runtime_id, fingerprint)
        manifest = self.load_manifest(job_id)
        return self.reconcile(manifest) if manifest else None

    def load_manifest(self, job_id: str) -> Optional[Dict]:
        path = self._manifest_path(job_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def save_manifest(self, manifest: Dict) -> Dict:
        updated = dict(manifest)
        updated["updated_at"] = _utc_now()
        self._atomic_write_json(self._manifest_path(updated["job_id"]), updated)
        return updated

    def reconcile(self, manifest: Dict) -> Dict:
        """Recover chunk files written immediately before an interruption."""
        reconciled = dict(manifest)
        job_id = reconciled["job_id"]
        total_chunks = int(reconciled.get("total_chunks", 0))
        completed = [
            index
            for index in range(total_chunks)
            if self._chunk_path(job_id, index).exists()
        ]
        completed_rows = 0
        for index in completed:
            start = index * int(reconciled["chunk_size"])
            completed_rows += min(
                int(reconciled["chunk_size"]),
                max(0, int(reconciled["total_rows"]) - start),
            )
        changed = (
            completed != list(reconciled.get("completed_chunks", []))
            or completed_rows != int(reconciled.get("completed_rows", 0))
        )
        reconciled["completed_chunks"] = completed
        reconciled["completed_rows"] = completed_rows
        if len(completed) == total_chunks and total_chunks > 0:
            reconciled["status"] = "completed"
        elif reconciled.get("status") == "completed":
            reconciled["status"] = "running"
        return self.save_manifest(reconciled) if changed else reconciled

    def next_chunk_index(self, manifest: Dict) -> Optional[int]:
        completed = set(int(index) for index in manifest.get("completed_chunks", []))
        for index in range(int(manifest.get("total_chunks", 0))):
            if index not in completed:
                return index
        return None

    def chunk_frame(
        self,
        selected: pd.DataFrame,
        manifest: Dict,
        chunk_index: int,
    ) -> pd.DataFrame:
        start = int(chunk_index) * int(manifest["chunk_size"])
        stop = min(start + int(manifest["chunk_size"]), len(selected))
        return selected.iloc[start:stop].copy().reset_index(drop=True)

    def save_scraped_records(
        self,
        job_id: str,
        chunk_index: int,
        records: Iterable[Dict],
    ) -> None:
        """Temporarily save public scraper output, explicitly removing secret fields."""
        payload = [_json_safe(record) for record in records if isinstance(record, dict)]
        self._atomic_write_json(self._records_path(job_id, chunk_index), payload)

    def load_scraped_records(self, job_id: str, chunk_index: int) -> Optional[List[Dict]]:
        path = self._records_path(job_id, chunk_index)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, list) else None

    def discard_scraped_records(self, job_id: str, chunk_index: int) -> None:
        try:
            self._records_path(job_id, chunk_index).unlink(missing_ok=True)
        except OSError:
            pass

    def save_completed_chunk(
        self,
        manifest: Dict,
        chunk_index: int,
        tagged: pd.DataFrame,
        *,
        elapsed_seconds: float,
    ) -> Dict:
        """Save output before advancing the manifest, making resume idempotent."""
        job_id = manifest["job_id"]
        self._atomic_write_json(
            self._chunk_path(job_id, chunk_index),
            dataframe_to_payload(tagged.reset_index(drop=True)),
        )
        updated = dict(manifest)
        completed = set(int(index) for index in updated.get("completed_chunks", []))
        completed.add(int(chunk_index))
        updated["completed_chunks"] = sorted(completed)
        updated["completed_rows"] = min(
            int(updated["total_rows"]),
            sum(
                min(
                    int(updated["chunk_size"]),
                    max(0, int(updated["total_rows"]) - (index * int(updated["chunk_size"]))),
                )
                for index in completed
            ),
        )
        updated["elapsed_seconds"] = round(
            float(updated.get("elapsed_seconds", 0.0)) + max(0.0, float(elapsed_seconds)),
            2,
        )
        updated["last_error"] = ""
        updated["status"] = (
            "completed"
            if len(completed) >= int(updated["total_chunks"])
            else "running"
        )
        updated = self.save_manifest(updated)
        self.discard_scraped_records(job_id, chunk_index)
        return updated

    def mark_failed(self, manifest: Dict, error: str = "") -> Dict:
        """Pause a job without persisting raw exception text or credentials."""
        updated = dict(manifest)
        updated["status"] = "failed"
        updated["last_error"] = (
            "The current chunk stopped before completion. Resume is required."
        )
        return self.save_manifest(updated)

    def load_completed_results(self, manifest: Dict) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []
        job_id = manifest["job_id"]
        for index in sorted(int(item) for item in manifest.get("completed_chunks", [])):
            path = self._chunk_path(job_id, index)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            frame = dataframe_from_payload(payload)
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def delete_job(self, job_id: str) -> None:
        directory = self._job_dir(job_id)
        if directory.exists():
            shutil.rmtree(directory)
