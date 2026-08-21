"""Audit recorder (Phase 20 §33, §34).

Audit events are **append-oriented** and immutable: each event carries a hash
that chains to the previous event's hash (tamper-evident ordering). Corrections
are appended as new corrective events (with actor/source/reason/correlation),
never in-place edits. This is a provider-neutral abstraction that complements
the existing DB-backed ``audit_logs`` model; it does not replace it.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AuditEvent",
    "AuditRecorder",
    "InMemoryAuditRecorder",
    "NoopAuditRecorder",
    "get_audit_recorder",
    "reset_audit_recorder",
]


@dataclass
class AuditEvent:
    id: str
    event_type: str
    actor: str | None
    source: str
    status: str
    event_hash: str
    previous_event_hash: str | None
    timestamp: float = field(default_factory=time.time)
    reason: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "actor": self.actor,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "event_hash": self.event_hash,
            "previous_event_hash": self.previous_event_hash,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "fields": self.fields,
        }


def _hash_event(previous_hash: str | None, event_type: str, timestamp: float, fields: dict[str, Any]) -> str:
    payload = {
        "previous": previous_hash,
        "event_type": event_type,
        "timestamp": timestamp,
        "fields": fields,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditRecorder:
    """Append-only audit recorder interface."""

    def record(
        self,
        event_type: str,
        *,
        actor: str | None = None,
        source: str = "system",
        status: str = "ok",
        reason: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        **fields: Any,
    ) -> AuditEvent:
        raise NotImplementedError

    def events(self) -> list[dict]:
        raise NotImplementedError


class InMemoryAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._last_hash: str | None = None
        self._lock = threading.Lock()

    def record(self, event_type: str, **kwargs: Any) -> AuditEvent:
        timestamp = time.time()
        event_hash = _hash_event(self._last_hash, event_type, timestamp, kwargs.get("fields", {}))
        event = AuditEvent(
            id=uuid.uuid4().hex,
            event_type=event_type,
            actor=kwargs.get("actor"),
            source=kwargs.get("source", "system"),
            status=kwargs.get("status", "ok"),
            reason=kwargs.get("reason"),
            correlation_id=kwargs.get("correlation_id"),
            trace_id=kwargs.get("trace_id"),
            request_id=kwargs.get("request_id"),
            timestamp=timestamp,
            event_hash=event_hash,
            previous_event_hash=self._last_hash,
            fields=kwargs.get("fields", {}),
        )
        with self._lock:
            self._events.append(event)
            self._last_hash = event_hash
        return event

    def events(self) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self._events]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_hash = None


class NoopAuditRecorder(AuditRecorder):
    def record(self, event_type: str, **kwargs: Any) -> AuditEvent:
        return AuditEvent(
            id=uuid.uuid4().hex,
            event_type=event_type,
            actor=kwargs.get("actor"),
            source=kwargs.get("source", "system"),
            status=kwargs.get("status", "ok"),
            reason=kwargs.get("reason"),
            correlation_id=kwargs.get("correlation_id"),
            trace_id=kwargs.get("trace_id"),
            request_id=kwargs.get("request_id"),
            event_hash=_hash_event(None, event_type, time.time(), kwargs.get("fields", {})),
            previous_event_hash=None,
            fields=kwargs.get("fields", {}),
        )

    def events(self) -> list[dict]:
        return []


_recorder: AuditRecorder | None = None
_recorder_lock = threading.Lock()


def get_audit_recorder() -> AuditRecorder:
    global _recorder
    if _recorder is None:
        with _recorder_lock:
            if _recorder is None:
                _recorder = InMemoryAuditRecorder()
    return _recorder


def reset_audit_recorder() -> None:
    global _recorder
    with _recorder_lock:
        _recorder = None
