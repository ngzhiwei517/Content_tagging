"""Shared Apify usage safeguards for the internal beta deployment.

The guard is deliberately independent of Streamlit so every paid Actor entry
point can use the same policy. Tokens are sent only in an authorization header
and are never stored in status snapshots, lock metadata, or checkpoints.
"""

from __future__ import annotations

import hashlib
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

import requests


APIFY_LIMITS_URL = "https://api.apify.com/v2/users/me/limits"
DEFAULT_WARNING_USD = 3.50
DEFAULT_STOP_USD = 4.00


class ApifyGuardError(RuntimeError):
    """Base class for safe, user-readable Apify fallback interruptions."""


class ApifyUsageBlockedError(ApifyGuardError):
    """Raised before a paid Actor starts at the configured safety threshold."""


class ApifyUsageUnavailableError(ApifyGuardError):
    """Raised when usage cannot be verified and fail-closed mode is enabled."""


class ApifyFallbackBusyError(ApifyGuardError):
    """Raised when another beta session currently owns the paid-call slot."""


@dataclass(frozen=True)
class ApifyGuardConfig:
    enabled: bool = True
    warning_usd: float = DEFAULT_WARNING_USD
    stop_usd: float = DEFAULT_STOP_USD
    fail_closed: bool = True
    usage_cache_seconds: float = 60.0
    request_timeout_seconds: float = 8.0

    def normalized(self) -> "ApifyGuardConfig":
        warning = max(float(self.warning_usd), 0.0)
        stop = max(float(self.stop_usd), 0.01)
        return ApifyGuardConfig(
            enabled=bool(self.enabled),
            warning_usd=min(warning, stop),
            stop_usd=stop,
            fail_closed=bool(self.fail_closed),
            usage_cache_seconds=max(float(self.usage_cache_seconds), 0.0),
            request_timeout_seconds=max(float(self.request_timeout_seconds), 1.0),
        )


@dataclass(frozen=True)
class ApifyUsageSnapshot:
    monthly_usage_usd: float
    max_monthly_usage_usd: float
    cycle_start_at: str = ""
    cycle_end_at: str = ""
    active_actor_job_count: int = 0
    checked_at: str = ""

    @property
    def remaining_usd(self) -> float:
        if self.max_monthly_usage_usd <= 0:
            return 0.0
        return max(self.max_monthly_usage_usd - self.monthly_usage_usd, 0.0)


_CONFIG = ApifyGuardConfig().normalized()
_CONFIG_LOCK = threading.Lock()
_USAGE_CACHE: Dict[str, tuple[float, ApifyUsageSnapshot]] = {}
_USAGE_CACHE_LOCK = threading.Lock()
_APIFY_FALLBACK_LOCK = threading.Lock()
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_CALL: Dict[str, object] = {}


def configure_apify_guard(config: ApifyGuardConfig) -> ApifyGuardConfig:
    """Set the process-wide beta policy without retaining provider secrets."""
    normalized = config.normalized()
    global _CONFIG
    with _CONFIG_LOCK:
        _CONFIG = normalized
    return normalized


def current_apify_guard_config() -> ApifyGuardConfig:
    with _CONFIG_LOCK:
        return _CONFIG


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def fetch_apify_usage(
    token: str,
    *,
    timeout_seconds: Optional[float] = None,
    http_get: Optional[Callable] = None,
) -> ApifyUsageSnapshot:
    """Read the current account usage and limit from Apify's private API."""
    clean_token = str(token or "").strip()
    if not clean_token:
        raise ApifyUsageUnavailableError(
            "APIFY_USAGE_CHECK_UNAVAILABLE: Apify fallback is not configured."
        )

    config = current_apify_guard_config()
    request_get = http_get or requests.get
    try:
        response = request_get(
            APIFY_LIMITS_URL,
            headers={"Authorization": f"Bearer {clean_token}"},
            timeout=float(timeout_seconds or config.request_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        limits = data.get("limits", {}) if isinstance(data, dict) else {}
        current = data.get("current", {}) if isinstance(data, dict) else {}
        cycle = data.get("monthlyUsageCycle", {}) if isinstance(data, dict) else {}
        usage = float(current.get("monthlyUsageUsd"))
        maximum = float(limits.get("maxMonthlyUsageUsd"))
        active_jobs = int(current.get("activeActorJobCount", 0) or 0)
    except ApifyGuardError:
        raise
    except Exception as exc:
        raise ApifyUsageUnavailableError(
            "APIFY_USAGE_CHECK_UNAVAILABLE: Shared Apify usage could not be "
            "verified, so new paid fallback work is paused safely."
        ) from exc

    return ApifyUsageSnapshot(
        monthly_usage_usd=max(usage, 0.0),
        max_monthly_usage_usd=max(maximum, 0.0),
        cycle_start_at=str(cycle.get("startAt", "") or ""),
        cycle_end_at=str(cycle.get("endAt", "") or ""),
        active_actor_job_count=max(active_jobs, 0),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def get_apify_usage(
    token: str,
    *,
    force: bool = False,
    fetcher: Optional[Callable[[str], ApifyUsageSnapshot]] = None,
) -> ApifyUsageSnapshot:
    """Return a short-lived cached usage snapshot without caching the token."""
    clean_token = str(token or "").strip()
    fingerprint = _token_fingerprint(clean_token)
    now = time.monotonic()
    config = current_apify_guard_config()
    if not force and config.usage_cache_seconds > 0:
        with _USAGE_CACHE_LOCK:
            cached = _USAGE_CACHE.get(fingerprint)
        if cached and now - cached[0] <= config.usage_cache_seconds:
            return cached[1]

    snapshot = (fetcher or fetch_apify_usage)(clean_token)
    with _USAGE_CACHE_LOCK:
        _USAGE_CACHE[fingerprint] = (now, snapshot)
    return snapshot


def effective_stop_usd(
    snapshot: ApifyUsageSnapshot,
    config: Optional[ApifyGuardConfig] = None,
) -> float:
    policy = (config or current_apify_guard_config()).normalized()
    if snapshot.max_monthly_usage_usd > 0:
        return min(policy.stop_usd, snapshot.max_monthly_usage_usd)
    return policy.stop_usd


def apify_capacity_state(
    snapshot: ApifyUsageSnapshot,
    config: Optional[ApifyGuardConfig] = None,
) -> str:
    """Return ``available``, ``warning`` or ``blocked`` for one snapshot."""
    policy = (config or current_apify_guard_config()).normalized()
    stop = effective_stop_usd(snapshot, policy)
    warning = min(policy.warning_usd, stop)
    if snapshot.monthly_usage_usd >= stop:
        return "blocked"
    if snapshot.monthly_usage_usd >= warning:
        return "warning"
    return "available"


def active_apify_fallback() -> Dict[str, object]:
    """Return non-sensitive metadata for the current in-process paid call."""
    with _ACTIVE_LOCK:
        return dict(_ACTIVE_CALL)


@contextmanager
def apify_fallback_slot(
    token: str,
    *,
    purpose: str,
    owner_id: str = "",
    usage_provider: Optional[Callable[[str], ApifyUsageSnapshot]] = None,
):
    """Serialize and preflight one paid Actor call for the shared beta account."""
    config = current_apify_guard_config()
    if not config.enabled or not str(token or "").strip():
        yield None
        return

    if not _APIFY_FALLBACK_LOCK.acquire(blocking=False):
        raise ApifyFallbackBusyError(
            "APIFY_FALLBACK_BUSY: Another beta user is currently using Apify "
            "fallback. Completed progress is safe; retry shortly."
        )

    try:
        try:
            provider = usage_provider or (
                lambda value: get_apify_usage(value, force=True)
            )
            snapshot = provider(str(token or "").strip())
        except ApifyGuardError:
            if config.fail_closed:
                raise
            snapshot = None
        except Exception as exc:
            if config.fail_closed:
                raise ApifyUsageUnavailableError(
                    "APIFY_USAGE_CHECK_UNAVAILABLE: Shared Apify usage could not "
                    "be verified, so new paid fallback work is paused safely."
                ) from exc
            snapshot = None

        if snapshot is not None and apify_capacity_state(snapshot, config) == "blocked":
            raise ApifyUsageBlockedError(
                "APIFY_BETA_USAGE_LIMIT: Shared Apify fallback reached the beta "
                "safety threshold. Direct retrieval remains available and "
                "completed progress is saved."
            )
        if snapshot is not None and snapshot.active_actor_job_count > 0:
            raise ApifyFallbackBusyError(
                "APIFY_FALLBACK_BUSY: The shared Apify account already has an "
                "active Actor job. Completed progress is safe; retry shortly."
            )

        with _ACTIVE_LOCK:
            _ACTIVE_CALL.clear()
            _ACTIVE_CALL.update({
                "purpose": str(purpose or "Apify fallback"),
                "owner_id": str(owner_id or ""),
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        yield snapshot
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_CALL.clear()
        _APIFY_FALLBACK_LOCK.release()


def _reset_apify_guard_for_tests() -> None:
    """Reset process state for deterministic unit tests."""
    configure_apify_guard(ApifyGuardConfig())
    with _USAGE_CACHE_LOCK:
        _USAGE_CACHE.clear()
    with _ACTIVE_LOCK:
        _ACTIVE_CALL.clear()
