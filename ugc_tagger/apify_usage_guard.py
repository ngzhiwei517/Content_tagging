"""Shared Apify usage safeguards for the internal beta deployment.

The guard is deliberately independent of Streamlit so every paid Actor entry
point can use the same policy. Tokens are sent only in an authorization header
and are never stored in status snapshots, lock metadata, or checkpoints.
"""

from __future__ import annotations

import hashlib
import logging
import os
import smtplib
import ssl
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Dict, Optional

import requests


APIFY_LIMITS_URL = "https://api.apify.com/v2/users/me/limits"
DEFAULT_WARNING_USD = 8.00
DEFAULT_STOP_USD = 8.70
DEFAULT_EMERGENCY_STOP_USD = 9.50
LOGGER = logging.getLogger(__name__)


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
    emergency_stop_usd: float = DEFAULT_EMERGENCY_STOP_USD
    fail_closed: bool = True
    usage_cache_seconds: float = 60.0
    request_timeout_seconds: float = 8.0

    def normalized(self) -> "ApifyGuardConfig":
        warning = max(float(self.warning_usd), 0.0)
        stop = max(float(self.stop_usd), 0.01)
        emergency = max(float(self.emergency_stop_usd), stop)
        return ApifyGuardConfig(
            enabled=bool(self.enabled),
            warning_usd=min(warning, stop),
            stop_usd=stop,
            emergency_stop_usd=emergency,
            fail_closed=bool(self.fail_closed),
            usage_cache_seconds=max(float(self.usage_cache_seconds), 0.0),
            request_timeout_seconds=max(float(self.request_timeout_seconds), 1.0),
        )


@dataclass(frozen=True)
class ApifyOwnerEmailConfig:
    """Server-only SMTP settings for private owner usage alerts."""

    enabled: bool = False
    owner_email: str = ""
    sender_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = field(default="", repr=False)
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 10.0
    state_dir: str = ".tmp/apify_guard_alerts"

    def is_ready(self) -> bool:
        return bool(
            self.enabled
            and self.owner_email.strip()
            and (self.sender_email.strip() or self.smtp_username.strip())
            and self.smtp_host.strip()
            and int(self.smtp_port) > 0
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
_EMAIL_CONFIG = ApifyOwnerEmailConfig()
_CONFIG_LOCK = threading.Lock()
_USAGE_CACHE: Dict[str, tuple[float, ApifyUsageSnapshot]] = {}
_USAGE_CACHE_LOCK = threading.Lock()
_APIFY_FALLBACK_LOCK = threading.Lock()
_BATCH_OWNER_CONTEXT: ContextVar[str] = ContextVar(
    "apify_batch_owner",
    default="",
)
_ADMISSION_LOCK = threading.Lock()
_ADMISSION_STATE: Dict[str, str] = {
    "cycle": "",
    "candidate_owner": "",
    "admitted_owner": "",
}
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_CALL: Dict[str, object] = {}
_EMAIL_ALERT_LOCK = threading.Lock()
_EMAIL_RETRY_AFTER: Dict[str, float] = {}


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


def configure_apify_owner_email(
    config: ApifyOwnerEmailConfig,
) -> ApifyOwnerEmailConfig:
    """Set server-only owner notification settings for this app process."""
    global _EMAIL_CONFIG
    with _CONFIG_LOCK:
        _EMAIL_CONFIG = config
    return config


def current_apify_owner_email_config() -> ApifyOwnerEmailConfig:
    with _CONFIG_LOCK:
        return _EMAIL_CONFIG


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


def effective_emergency_stop_usd(
    snapshot: ApifyUsageSnapshot,
    config: Optional[ApifyGuardConfig] = None,
) -> float:
    policy = (config or current_apify_guard_config()).normalized()
    if snapshot.max_monthly_usage_usd > 0:
        return min(policy.emergency_stop_usd, snapshot.max_monthly_usage_usd)
    return policy.emergency_stop_usd


def apify_capacity_state(
    snapshot: ApifyUsageSnapshot,
    config: Optional[ApifyGuardConfig] = None,
) -> str:
    """Return available, warning, restricted, or blocked for one snapshot."""
    policy = (config or current_apify_guard_config()).normalized()
    stop = effective_stop_usd(snapshot, policy)
    emergency = effective_emergency_stop_usd(snapshot, policy)
    warning = min(policy.warning_usd, stop)
    if snapshot.monthly_usage_usd >= emergency:
        return "blocked"
    if snapshot.monthly_usage_usd >= stop:
        return "restricted"
    if snapshot.monthly_usage_usd >= warning:
        return "warning"
    return "available"


def _usage_cycle_id(snapshot: ApifyUsageSnapshot) -> str:
    return (
        snapshot.cycle_start_at
        or snapshot.cycle_end_at
        or str(snapshot.checked_at or "")[:7]
        or "unknown-cycle"
    )


@contextmanager
def apify_batch_owner(owner_id: str):
    """Attach a stable, non-secret batch identity to nested Actor calls."""
    token = _BATCH_OWNER_CONTEXT.set(str(owner_id or "").strip())
    try:
        yield
    finally:
        _BATCH_OWNER_CONTEXT.reset(token)


def _resolved_owner_id(owner_id: str) -> str:
    return str(owner_id or _BATCH_OWNER_CONTEXT.get() or "").strip()


def _reset_admission_cycle_locked(snapshot: ApifyUsageSnapshot) -> None:
    cycle = _usage_cycle_id(snapshot)
    if _ADMISSION_STATE.get("cycle") == cycle:
        return
    _ADMISSION_STATE.clear()
    _ADMISSION_STATE.update(
        cycle=cycle,
        candidate_owner="",
        admitted_owner="",
    )


def _remember_admission_candidate(
    snapshot: ApifyUsageSnapshot,
    owner_id: str,
) -> None:
    if not owner_id:
        return
    with _ADMISSION_LOCK:
        _reset_admission_cycle_locked(snapshot)
        if not _ADMISSION_STATE.get("admitted_owner"):
            _ADMISSION_STATE["candidate_owner"] = owner_id


def _owner_is_admitted(
    snapshot: ApifyUsageSnapshot,
    owner_id: str,
) -> bool:
    if not owner_id:
        return False
    with _ADMISSION_LOCK:
        _reset_admission_cycle_locked(snapshot)
        admitted = _ADMISSION_STATE.get("admitted_owner", "")
        if not admitted:
            admitted = _ADMISSION_STATE.get("candidate_owner", "")
            if admitted:
                _ADMISSION_STATE["admitted_owner"] = admitted
        return bool(admitted and owner_id == admitted)


def _alert_key(
    snapshot: ApifyUsageSnapshot,
    state: str,
    owner_email: str = "",
) -> str:
    cycle = _usage_cycle_id(snapshot)
    recipient = str(owner_email or "").strip().lower()
    return hashlib.sha256(
        f"{cycle}|{state}|{recipient}".encode("utf-8")
    ).hexdigest()


def _alert_marker_path(config: ApifyOwnerEmailConfig, key: str) -> Path:
    return Path(config.state_dir) / f"{key}.sent"


def _reached_alert_states(
    snapshot: ApifyUsageSnapshot,
    config: ApifyGuardConfig,
) -> list[str]:
    """Return every threshold state reached by the latest usage snapshot."""
    warning = min(config.warning_usd, effective_stop_usd(snapshot, config))
    stop = effective_stop_usd(snapshot, config)
    emergency = effective_emergency_stop_usd(snapshot, config)
    states = []
    if snapshot.monthly_usage_usd >= warning:
        states.append("warning")
    if snapshot.monthly_usage_usd >= stop:
        states.append("restricted")
    if snapshot.monthly_usage_usd >= emergency:
        states.append("blocked")
    return states


def _owner_alert_message(
    snapshot: ApifyUsageSnapshot,
    state: str,
    config: ApifyGuardConfig,
    email_config: ApifyOwnerEmailConfig,
) -> EmailMessage:
    stop = effective_stop_usd(snapshot, config)
    emergency = effective_emergency_stop_usd(snapshot, config)
    warning = min(config.warning_usd, stop)
    blocked = state == "blocked"
    restricted = state == "restricted"
    message = EmailMessage()
    message["To"] = email_config.owner_email.strip()
    message["From"] = (
        email_config.sender_email.strip()
        or email_config.smtp_username.strip()
    )
    message["Subject"] = (
        "[Tagger] Apify fallback paused at the safety threshold"
        if blocked
        else (
            "[Tagger] New Apify batches restricted"
            if restricted
            else "[Tagger] Apify usage warning threshold reached"
        )
    )
    threshold = emergency if blocked else (stop if restricted else warning)
    action = (
        "New paid Apify Actor starts are now blocked by the app."
        if blocked
        else (
            "New paid batches are restricted to the already-admitted batch. "
            f"All paid starts stop at ${emergency:.2f}."
            if restricted
            else f"New paid batches will be restricted at ${stop:.2f}."
        )
    )
    message.set_content(
        "This is an automatic private alert from the UGC Post Tagging Tool.\n\n"
        f"Current monthly Apify usage: ${snapshot.monthly_usage_usd:.2f}\n"
        f"Alert threshold: ${threshold:.2f}\n"
        f"Configured account limit: ${snapshot.max_monthly_usage_usd:.2f}\n"
        f"Usage cycle ends: {snapshot.cycle_end_at or 'Not available'}\n"
        f"Active Actor jobs reported by Apify: {snapshot.active_actor_job_count}\n\n"
        f"{action}\n"
        "Direct-only retrieval remains available and completed batch progress is saved.\n"
        "Review Apify Billing and the beta workload before changing the threshold.\n"
    )
    return message


def _send_owner_email(
    message: EmailMessage,
    config: ApifyOwnerEmailConfig,
    *,
    smtp_factory: Optional[Callable] = None,
) -> None:
    factory = smtp_factory
    if factory is None:
        factory = smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP
    client = factory(
        config.smtp_host.strip(),
        int(config.smtp_port),
        timeout=max(float(config.timeout_seconds), 1.0),
    )
    try:
        if config.use_tls and not config.use_ssl:
            client.starttls(context=ssl.create_default_context())
        if config.smtp_username.strip():
            client.login(
                config.smtp_username.strip(),
                config.smtp_password,
            )
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            pass


def notify_apify_owner_if_needed(
    snapshot: ApifyUsageSnapshot,
    *,
    guard_config: Optional[ApifyGuardConfig] = None,
    email_config: Optional[ApifyOwnerEmailConfig] = None,
    smtp_factory: Optional[Callable] = None,
) -> str:
    """Send one private email per usage cycle and threshold state."""
    policy = (guard_config or current_apify_guard_config()).normalized()
    mail = email_config or current_apify_owner_email_config()
    reached_states = _reached_alert_states(snapshot, policy)
    if not reached_states:
        return "not_needed"
    if not mail.is_ready():
        return "not_configured"

    sent_any = False
    failed_any = False
    retry_later = False
    with _EMAIL_ALERT_LOCK:
        for state in reached_states:
            key = _alert_key(snapshot, state, mail.owner_email)
            marker = _alert_marker_path(mail, key)
            if marker.exists():
                continue
            retry_after = _EMAIL_RETRY_AFTER.get(key, 0.0)
            if time.monotonic() < retry_after:
                retry_later = True
                continue
            try:
                message = _owner_alert_message(snapshot, state, policy, mail)
                _send_owner_email(message, mail, smtp_factory=smtp_factory)
                marker.parent.mkdir(parents=True, exist_ok=True)
                temporary = marker.with_suffix(
                    f".{os.getpid()}.{threading.get_ident()}.tmp"
                )
                temporary.write_text(
                    datetime.now(timezone.utc).isoformat(),
                    encoding="utf-8",
                )
                temporary.replace(marker)
                _EMAIL_RETRY_AFTER.pop(key, None)
                sent_any = True
            except Exception as exc:
                _EMAIL_RETRY_AFTER[key] = time.monotonic() + 300.0
                failed_any = True
                LOGGER.warning(
                    "Apify owner alert email could not be sent (%s).",
                    exc.__class__.__name__,
                )
    if failed_any:
        return "failed"
    if sent_any:
        return "sent"
    if retry_later:
        return "retry_later"
    return "already_sent"


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
    resolved_owner = _resolved_owner_id(owner_id)
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

        if snapshot is not None:
            notify_apify_owner_if_needed(snapshot, guard_config=config)
            capacity_state = apify_capacity_state(snapshot, config)
            if capacity_state == "blocked":
                raise ApifyUsageBlockedError(
                    "APIFY_BETA_USAGE_LIMIT: Shared Apify fallback reached the "
                    "emergency safety threshold. Direct retrieval remains "
                    "available and completed progress is saved."
                )
            if capacity_state == "restricted" and not _owner_is_admitted(
                snapshot,
                resolved_owner,
            ):
                raise ApifyUsageBlockedError(
                    "APIFY_BETA_USAGE_LIMIT: New paid fallback batches are "
                    "temporarily restricted. Direct retrieval remains available "
                    "and completed progress is saved."
                )
        if snapshot is not None and snapshot.active_actor_job_count > 0:
            raise ApifyFallbackBusyError(
                "APIFY_FALLBACK_BUSY: The shared Apify account already has an "
                "active Actor job. Completed progress is safe; retry shortly."
            )
        if snapshot is not None and apify_capacity_state(snapshot, config) in {
            "available",
            "warning",
        }:
            _remember_admission_candidate(snapshot, resolved_owner)

        with _ACTIVE_LOCK:
            _ACTIVE_CALL.clear()
            _ACTIVE_CALL.update({
                "purpose": str(purpose or "Apify fallback"),
                "owner_id": resolved_owner,
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
    configure_apify_owner_email(ApifyOwnerEmailConfig())
    with _USAGE_CACHE_LOCK:
        _USAGE_CACHE.clear()
    with _ACTIVE_LOCK:
        _ACTIVE_CALL.clear()
    with _EMAIL_ALERT_LOCK:
        _EMAIL_RETRY_AFTER.clear()
    with _ADMISSION_LOCK:
        _ADMISSION_STATE.clear()
        _ADMISSION_STATE.update(
            cycle="",
            candidate_owner="",
            admitted_owner="",
        )
    _BATCH_OWNER_CONTEXT.set("")
