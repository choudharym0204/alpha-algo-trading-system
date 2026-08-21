"""Alerting abstraction (Phase 20 §29, §30, §31, §32, §52, §53).

* **Deterministic identity** for deduplication: the same condition (type +
  source + scope + condition key) yields the same identity, so it never creates
  unlimited duplicate alerts (§30). A random UUID is never the sole identity.
* **Lifecycle** with auditable transitions: DETECTED → ACTIVE →
  (ACKNOWLEDGED | ESCALATED) → RESOLVED (§31). Every transition is recorded.
* Provider-neutral in-memory store; a no-op manager is available for tests and
  for when the alert backend is unavailable (§42).
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "AlertSeverity",
    "AlertState",
    "Alert",
    "AlertManager",
    "NoopAlertManager",
    "get_alert_manager",
    "reset_alert_manager",
]


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class AlertState(str, Enum):
    DETECTED = "detected"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


def alert_identity(*, alert_type: str, source: str, scope: str, condition: str) -> str:
    """Deterministic identity from (type, source, scope, condition)."""
    raw = f"{alert_type}|{source}|{scope}|{condition}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Alert:
    id: str
    identity: str
    alert_type: str
    severity: AlertSeverity
    source: str
    scope: str
    condition: str
    title: str
    message: str
    state: AlertState = AlertState.DETECTED
    incident_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    transitions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "identity": self.identity,
            "type": self.alert_type,
            "severity": self.severity.value,
            "source": self.source,
            "scope": self.scope,
            "condition": self.condition,
            "title": self.title,
            "message": self.message,
            "state": self.state.value,
            "incident_id": self.incident_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "transitions": list(self.transitions),
        }


class AlertManager:
    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._by_identity: dict[str, str] = {}
        self._lock = threading.Lock()

    def trigger(
        self,
        *,
        alert_type: str,
        severity: AlertSeverity,
        source: str,
        scope: str,
        condition: str,
        title: str,
        message: str,
        incident_id: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> Alert:
        """Create an alert or return the existing open one (deduplication)."""
        identity = alert_identity(
            alert_type=alert_type, source=source, scope=scope, condition=condition
        )
        with self._lock:
            existing_id = self._by_identity.get(identity)
            if existing_id is not None:
                existing = self._alerts[existing_id]
                if existing.state not in (AlertState.RESOLVED,):
                    return existing
            alert = Alert(
                id=uuid.uuid4().hex,
                identity=identity,
                alert_type=alert_type,
                severity=severity,
                source=source,
                scope=scope,
                condition=condition,
                title=title,
                message=message,
                incident_id=incident_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
            )
            alert.transitions.append(
                {"from": None, "to": AlertState.DETECTED.value, "at": alert.created_at}
            )
            self._alerts[alert.id] = alert
            self._by_identity[identity] = alert.id
            return alert

    def _transition(self, alert_id: str, to: AlertState) -> Alert | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            alert.transitions.append(
                {"from": alert.state.value, "to": to.value, "at": time.time()}
            )
            alert.state = to
            alert.updated_at = time.time()
            return alert

    def acknowledge(self, alert_id: str) -> Alert | None:
        return self._transition(alert_id, AlertState.ACKNOWLEDGED)

    def escalate(self, alert_id: str) -> Alert | None:
        return self._transition(alert_id, AlertState.ESCALATED)

    def resolve(self, alert_id: str) -> Alert | None:
        return self._transition(alert_id, AlertState.RESOLVED)

    def get(self, alert_id: str) -> Alert | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def list(self, *, state: AlertState | None = None) -> list[dict]:
        with self._lock:
            alerts = list(self._alerts.values())
        if state is not None:
            alerts = [a for a in alerts if a.state == state]
        return [a.to_dict() for a in sorted(alerts, key=lambda a: a.created_at)]

    def clear(self) -> None:
        with self._lock:
            self._alerts.clear()
            self._by_identity.clear()


class NoopAlertManager(AlertManager):
    """Accepts trigger/transitions but records nothing (offline/tests)."""

    def trigger(self, **kwargs) -> Alert:
        identity = alert_identity(
            alert_type=kwargs["alert_type"],
            source=kwargs["source"],
            scope=kwargs["scope"],
            condition=kwargs["condition"],
        )
        return Alert(
            id=uuid.uuid4().hex,
            identity=identity,
            alert_type=kwargs["alert_type"],
            severity=kwargs["severity"],
            source=kwargs["source"],
            scope=kwargs["scope"],
            condition=kwargs["condition"],
            title=kwargs["title"],
            message=kwargs["message"],
        )

    def _transition(self, alert_id: str, to: AlertState) -> Alert | None:
        return None

    def acknowledge(self, alert_id: str) -> Alert | None:
        return None

    def escalate(self, alert_id: str) -> Alert | None:
        return None

    def resolve(self, alert_id: str) -> Alert | None:
        return None

    def list(self, *, state: AlertState | None = None) -> list[dict]:
        return []


_manager: AlertManager | None = None
_manager_lock = threading.Lock()


def get_alert_manager() -> AlertManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = AlertManager()
    return _manager


def reset_alert_manager() -> None:
    global _manager
    with _manager_lock:
        _manager = None
