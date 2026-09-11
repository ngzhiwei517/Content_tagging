"""One-at-a-time admission control for paid tagging work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .batch_checkpoint import BatchCheckpointStore


class TaggingWorkerQueueUnavailable(RuntimeError):
    """Raised when a configured shared queue cannot safely admit work."""


@dataclass(frozen=True)
class TaggingWorkerClaim:
    acquired: bool
    queue_position: int = 0
    active_recovery_id: str = ""
    lease_until: str = ""
    distributed: bool = False


def _claim_from_payload(payload: Dict[str, Any]) -> TaggingWorkerClaim:
    if not isinstance(payload, dict) or "acquired" not in payload:
        raise TaggingWorkerQueueUnavailable(
            "The shared tagging queue returned an invalid response."
        )
    try:
        position = max(0, int(payload.get("queue_position", 0) or 0))
    except (TypeError, ValueError):
        position = 0
    return TaggingWorkerClaim(
        acquired=bool(payload.get("acquired")),
        queue_position=position,
        active_recovery_id=str(payload.get("active_recovery_id", "") or ""),
        lease_until=str(payload.get("lease_until", "") or ""),
        distributed=True,
    )


class TaggingWorkerQueue:
    """Use a database FIFO queue, with a process-local fallback for local use."""

    def __init__(
        self,
        store: BatchCheckpointStore,
        *,
        persistent_backend=None,
        persistent_required: bool = False,
    ) -> None:
        self.store = store
        self.persistent_backend = persistent_backend
        self.persistent_required = bool(persistent_required)

    def claim(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: int = 7200,
    ) -> TaggingWorkerClaim:
        if self.persistent_backend is not None:
            claim = getattr(
                self.persistent_backend,
                "claim_tagging_worker",
                None,
            )
            if not callable(claim):
                raise TaggingWorkerQueueUnavailable(
                    "The deployed checkpoint backend does not support the shared queue."
                )
            try:
                return _claim_from_payload(
                    claim(
                        recovery_id,
                        job_id,
                        owner_id,
                        lease_seconds=lease_seconds,
                    )
                )
            except TaggingWorkerQueueUnavailable:
                raise
            except Exception as exc:
                raise TaggingWorkerQueueUnavailable(
                    "The shared tagging queue could not be reached."
                ) from exc

        if self.persistent_required:
            raise TaggingWorkerQueueUnavailable(
                "Persistent checkpoints are configured, but the shared queue is unavailable."
            )

        try:
            acquired = self.store.try_acquire_global_execution(
                recovery_id,
                job_id,
                owner_id,
                lease_seconds=lease_seconds,
            )
        except Exception as exc:
            raise TaggingWorkerQueueUnavailable(
                "The local tagging worker safeguard could not be created."
            ) from exc
        return TaggingWorkerClaim(
            acquired=acquired,
            queue_position=0 if acquired else 2,
            distributed=False,
        )

    def release(
        self,
        recovery_id: str,
        job_id: str,
        owner_id: str,
    ) -> None:
        if self.persistent_backend is not None:
            release = getattr(
                self.persistent_backend,
                "release_tagging_worker",
                None,
            )
            if not callable(release):
                return
            release(recovery_id, job_id, owner_id)
            return
        self.store.release_global_execution(recovery_id, job_id, owner_id)
