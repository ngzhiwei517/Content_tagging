"""Non-blocking, coalescing remote checkpoint writes.

Streamlit reruns must not wait for an optional remote recovery copy.  This
coordinator serializes writes for the same recovery ID, keeps only the newest
pending payload, and allows unrelated recovery IDs to save concurrently.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class _WriteRequest:
    digest: str
    operation: Callable[[], None]
    future: Future


@dataclass
class _WriteState:
    pending: Optional[_WriteRequest] = None
    running: Optional[_WriteRequest] = None
    saved_digest: str = ""
    status: str = "idle"
    last_error: Optional[Exception] = None
    active: bool = False
    updated_at: float = 0.0


class AsyncCheckpointWriter:
    """Run recovery writes away from Streamlit session threads.

    Different recovery IDs can use separate workers.  For one recovery ID,
    writes remain ordered and intermediate pending payloads are superseded by
    the newest state so rapid widget reruns do not flood the database.
    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="checkpoint-save",
        )
        self._lock = threading.RLock()
        self._states: Dict[str, _WriteState] = {}

    @staticmethod
    def _completed(value: str) -> Future:
        future = Future()
        future.set_result(value)
        return future

    def submit(
        self,
        key: str,
        digest: str,
        operation: Callable[[], None],
    ) -> Future:
        """Schedule one write and return immediately with its result future."""
        key = str(key or "").strip()
        digest = str(digest or "").strip()
        if not key or not digest or not callable(operation):
            raise ValueError("Checkpoint write key, digest and operation are required.")

        with self._lock:
            state = self._states.setdefault(key, _WriteState())
            state.updated_at = time.monotonic()
            if state.saved_digest == digest:
                return self._completed("saved")
            if state.running is not None and state.running.digest == digest:
                return state.running.future
            if state.pending is not None and state.pending.digest == digest:
                return state.pending.future

            request = _WriteRequest(digest, operation, Future())
            if state.pending is not None and not state.pending.future.done():
                state.pending.future.set_result("superseded")
            state.pending = request
            state.status = "queued"
            state.last_error = None
            if not state.active:
                state.active = True
                self._executor.submit(self._drain, key)
            return request.future

    def _drain(self, key: str) -> None:
        while True:
            with self._lock:
                state = self._states[key]
                request = state.pending
                if request is None:
                    state.active = False
                    if state.status == "saving":
                        state.status = "idle"
                    state.updated_at = time.monotonic()
                    return
                state.pending = None
                state.running = request
                state.status = "saving"
                state.updated_at = time.monotonic()

            error: Optional[Exception] = None
            try:
                request.operation()
            except Exception as exc:  # The caller reports a safe error category.
                error = exc

            with self._lock:
                state = self._states[key]
                state.running = None
                state.updated_at = time.monotonic()
                if error is None:
                    state.saved_digest = request.digest
                    state.last_error = None
                    state.status = "saved"
                    if not request.future.done():
                        request.future.set_result("saved")
                else:
                    state.last_error = error
                    state.status = "failed"
                    if not request.future.done():
                        request.future.set_exception(error)
                if state.pending is not None:
                    state.status = "queued"

    def status(self, key: str) -> Dict[str, object]:
        """Return a thread-safe snapshot for a later Streamlit rerun."""
        with self._lock:
            state = self._states.get(str(key or "").strip())
            if state is None:
                return {
                    "status": "idle",
                    "saved_digest": "",
                    "pending_digest": "",
                    "running_digest": "",
                    "error": None,
                }
            return {
                "status": state.status,
                "saved_digest": state.saved_digest,
                "pending_digest": state.pending.digest if state.pending else "",
                "running_digest": state.running.digest if state.running else "",
                "error": state.last_error,
            }

    def shutdown(self, *, wait: bool = True) -> None:
        """Release worker threads; primarily used by deterministic tests."""
        self._executor.shutdown(wait=wait)
