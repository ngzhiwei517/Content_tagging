"""Durable, secret-free checkpoints for large tagging batches.

The Streamlit entry point processes one chunk per script execution. This
module stores every completed post, completed chunk outputs and the current
chunk's scraped records under ``.tmp`` so a rerun or reconnect can continue
without repeating completed Gemini work.
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


CHECKPOINT_VERSION = 2
DEFAULT_CHUNK_SIZE = 50
DEFAULT_RETENTION_HOURS = 72
_SAFE_ID = re.compile(r"^[a-f0-9]{32}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_safe(value):
    """Return a JSON-compatible value without serialising credentials."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            key_normalized = re.sub(r"[^a-z0-9]+", "_", key_text.lower()).strip("_")
            if (
                "token" in key_normalized
                or "api_key" in key_normalized
                or key_normalized in {"authorization", "cookie", "cookies", "password", "secret"}
                or key_normalized in {
                    "downloaded_media",
                    "media_bytes",
                    "video_bytes",
                    "image_bytes",
                    "audio_bytes",
                    "local_media_path",
                    "local_video_path",
                    "local_image_path",
                    "local_audio_path",
                }
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
    blocked = re.compile(
        r"api[ _-]*key|token|secret|password|authorization|database[ _-]*url|connection[ _-]*string|"
        r"download(?:ed)?[ _-]*media|(?:media|video|image|audio)[ _-]*(?:bytes|blob)|"
        r"local[ _-]*(?:media|video|image|audio)[ _-]*path",
        re.IGNORECASE,
    )
    safe_columns = [column for column in df.columns if not blocked.search(str(column).strip())]
    df = df.loc[:, safe_columns].copy()
    df = df.map(lambda item: None if isinstance(item, (bytes, bytearray, memoryview)) else item)
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
        persistent_store=None,
    ) -> None:
        self.root = Path(root)
        self.chunk_size = max(1, int(chunk_size))
        self.retention_hours = max(1, int(retention_hours))
        self.persistent_store = persistent_store

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

    def _partial_dir(self, job_id: str, chunk_index: int) -> Path:
        return self._job_dir(job_id) / f"partial_{int(chunk_index):05d}"

    def _partial_row_path(
        self,
        job_id: str,
        chunk_index: int,
        row_position: int,
    ) -> Path:
        return self._partial_dir(job_id, chunk_index) / f"row_{int(row_position):05d}.json"

    @staticmethod
    def _write_local_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _object_key(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _atomic_write_json(self, path: Path, payload) -> bool:
        """Write locally and report whether the optional remote copy succeeded.

        Local checkpoints remain the fallback when persistent storage is not
        configured or temporarily unavailable.  Callers that compact several
        remote objects into one larger object use the return value to avoid
        deleting the smaller recovery copies before the larger copy is durable.
        """
        self._write_local_json(path, payload)
        if self.persistent_store is not None:
            try:
                self.persistent_store.save(self._object_key(path), payload)
                return True
            except Exception:
                pass
        return False

    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        if self.persistent_store is None:
            return None
        try:
            payload = self.persistent_store.load(self._object_key(path))
            if isinstance(payload, (dict, list)):
                self._write_local_json(path, payload)
                return payload
        except Exception:
            pass
        return None

    def _hydrate_prefix(self, prefix: str) -> None:
        if self.persistent_store is None:
            return
        try:
            objects = self.persistent_store.list_prefix(prefix)
        except Exception:
            return
        for key, payload in objects.items():
            try:
                destination = self.root / Path(key)
                destination.relative_to(self.root)
                self._write_local_json(destination, payload)
            except (OSError, ValueError, TypeError):
                continue

    def _delete_remote(self, key: str) -> None:
        if self.persistent_store is not None:
            try:
                self.persistent_store.delete(key)
            except Exception:
                pass

    def _delete_remote_prefix(self, prefix: str) -> None:
        if self.persistent_store is not None:
            try:
                self.persistent_store.delete_prefix(prefix)
            except Exception:
                pass

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
            "partial_rows": 0,
            "saved_rows": 0,
            "comparison_run_id": str(comparison_run_id),
            "comparison_started_utc": str(comparison_started_utc),
            "elapsed_seconds": 0.0,
            "last_error": "",
            "pause_reason": "",
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
        payload = self._read_json(path)
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
        self._hydrate_prefix(f"{job_id}/")
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
        partial_rows = 0
        for index in range(total_chunks):
            if index in completed:
                continue
            partial_rows += len(self.partial_positions(job_id, index))
        saved_rows = min(
            int(reconciled.get("total_rows", 0)),
            completed_rows + partial_rows,
        )
        changed = (
            completed != list(reconciled.get("completed_chunks", []))
            or completed_rows != int(reconciled.get("completed_rows", 0))
            or partial_rows != int(reconciled.get("partial_rows", 0))
            or saved_rows != int(reconciled.get("saved_rows", 0))
        )
        reconciled["completed_chunks"] = completed
        reconciled["completed_rows"] = completed_rows
        reconciled["partial_rows"] = partial_rows
        reconciled["saved_rows"] = saved_rows
        if len(completed) == total_chunks and total_chunks > 0:
            reconciled["status"] = "completed"
            reconciled["pause_reason"] = ""
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
        payload = self._read_json(path)
        return payload if isinstance(payload, list) else None

    def discard_scraped_records(
        self,
        job_id: str,
        chunk_index: int,
        *,
        delete_remote: bool = True,
    ) -> None:
        path = self._records_path(job_id, chunk_index)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        if delete_remote:
            self._delete_remote(self._object_key(path))

    def save_partial_row(
        self,
        job_id: str,
        chunk_index: int,
        row_position: int,
        tagged_row,
    ) -> None:
        """Atomically save one completed row from the current chunk."""
        if int(row_position) < 0:
            raise ValueError("Partial row position must be non-negative.")
        if isinstance(tagged_row, pd.Series):
            frame = tagged_row.to_frame().T
        elif isinstance(tagged_row, dict):
            frame = pd.DataFrame([tagged_row])
        elif isinstance(tagged_row, pd.DataFrame):
            frame = tagged_row.copy()
        else:
            raise TypeError("Partial tagged output must be a row or DataFrame.")
        if len(frame) != 1:
            raise ValueError("A partial checkpoint must contain exactly one row.")
        self._atomic_write_json(
            self._partial_row_path(
                job_id,
                chunk_index,
                row_position,
            ),
            _json_safe(dataframe_to_payload(frame.reset_index(drop=True))),
        )

    def partial_positions(self, job_id: str, chunk_index: int) -> List[int]:
        """Return saved row positions for one incomplete chunk."""
        directory = self._partial_dir(job_id, chunk_index)
        self._hydrate_prefix(f"{job_id}/partial_{int(chunk_index):05d}/")
        if not directory.exists():
            return []
        positions: List[int] = []
        for path in directory.glob("row_*.json"):
            match = re.fullmatch(r"row_(\d{5})\.json", path.name)
            if match:
                positions.append(int(match.group(1)))
        return sorted(set(positions))

    def load_partial_chunk_results(
        self,
        job_id: str,
        chunk_index: int,
    ) -> pd.DataFrame:
        """Restore saved rows for one incomplete chunk in input order."""
        frames: List[pd.DataFrame] = []
        for position in self.partial_positions(job_id, chunk_index):
            path = self._partial_row_path(job_id, chunk_index, position)
            payload = self._read_json(path)
            if payload is None:
                continue
            frame = dataframe_from_payload(payload)
            if len(frame) == 1:
                frame = frame.copy()
                frame["_checkpoint_row_position"] = position
                frames.append(frame)
        if not frames:
            return pd.DataFrame()
        output = pd.concat(frames, ignore_index=True)
        return output.sort_values(
            "_checkpoint_row_position",
            kind="stable",
        ).reset_index(drop=True)

    def discard_partial_results(
        self,
        job_id: str,
        chunk_index: int,
        *,
        delete_remote: bool = True,
    ) -> None:
        directory = self._partial_dir(job_id, chunk_index)
        if directory.exists():
            shutil.rmtree(directory)
        if delete_remote:
            self._delete_remote_prefix(f"{job_id}/partial_{int(chunk_index):05d}/")

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
        remote_chunk_saved = self._atomic_write_json(
            self._chunk_path(job_id, chunk_index),
            _json_safe(dataframe_to_payload(tagged.reset_index(drop=True))),
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
        updated["partial_rows"] = 0
        updated["saved_rows"] = updated["completed_rows"]
        updated["elapsed_seconds"] = round(
            float(updated.get("elapsed_seconds", 0.0)) + max(0.0, float(elapsed_seconds)),
            2,
        )
        updated["last_error"] = ""
        updated["pause_reason"] = ""
        updated["status"] = (
            "completed"
            if len(completed) >= int(updated["total_chunks"])
            else "running"
        )
        updated = self.save_manifest(updated)
        # The row-level objects are the last durable recovery point when a
        # transient Supabase/Postgres failure prevents the compact chunk from
        # being uploaded.  Always clear local temporary objects after the local
        # chunk is written, but only remove their remote copies after the remote
        # chunk save is confirmed.  A replacement Streamlit process can then
        # rebuild the chunk without repeating completed Gemini work.
        self.discard_partial_results(
            job_id,
            chunk_index,
            delete_remote=remote_chunk_saved,
        )
        self.discard_scraped_records(
            job_id,
            chunk_index,
            delete_remote=remote_chunk_saved,
        )
        return updated

    def mark_paused(self, manifest: Dict, *, quota: bool = False) -> Dict:
        """Pause without persisting raw provider errors or credentials."""
        reconciled = self.reconcile(manifest)
        updated = dict(reconciled)
        updated["status"] = "paused_quota" if quota else "paused_error"
        updated["pause_reason"] = "quota" if quota else "interrupted"
        updated["last_error"] = (
            "API quota is unavailable. Resume after the app owner restores access."
            if quota
            else "Tagging stopped before completion. Resume is required."
        )
        return self.save_manifest(updated)

    def mark_failed(self, manifest: Dict, error: str = "") -> Dict:
        """Backward-compatible alias for a non-quota pause."""
        return self.mark_paused(manifest, quota=False)

    def load_completed_results(self, manifest: Dict) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []
        job_id = manifest["job_id"]
        for index in sorted(int(item) for item in manifest.get("completed_chunks", [])):
            path = self._chunk_path(job_id, index)
            payload = self._read_json(path)
            if payload is None:
                continue
            frame = dataframe_from_payload(payload)
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def load_saved_results(self, manifest: Dict) -> pd.DataFrame:
        """Return completed chunks plus saved rows from the first open chunk."""
        frames: List[pd.DataFrame] = []
        completed = self.load_completed_results(manifest)
        if not completed.empty:
            frames.append(completed)
        next_index = self.next_chunk_index(manifest)
        if next_index is not None:
            partial = self.load_partial_chunk_results(
                manifest["job_id"],
                next_index,
            )
            if not partial.empty:
                partial = partial.drop(
                    columns=["_checkpoint_row_position"],
                    errors="ignore",
                )
                frames.append(partial)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def delete_job(self, job_id: str) -> None:
        directory = self._job_dir(job_id)
        if directory.exists():
            shutil.rmtree(directory)
        self._delete_remote_prefix(f"{self._validated_job_id(job_id)}/")
