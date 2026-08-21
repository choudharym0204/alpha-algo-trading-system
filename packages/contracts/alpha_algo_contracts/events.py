"""Unified domain-event contract (Phase 21).

A single, validated envelope for the internal trading event flow so that the
pipeline (signal → risk → orchestration → OMS → execution → position →
portfolio → P&L → reconciliation) can be observed, correlated, and consumed by
cross-cutting subscribers (observability, audit, notification) without each
engine inventing its own event shape.

* Events are **append-only facts** describing something that already happened.
* They never mutate trading state and never carry secrets (Phase 20 §2/§38).
* Correlation is preserved via ``correlation_id`` / ``causation_id`` /
  ``trace_id`` and domain ids (``domain_ids``) — never replacing domain ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

__all__ = [
    "DomainEvent",
    "DomainEventError",
    "EventType",
    "create_event",
    "validate_no_secrets",
]

_SAFE_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.]{0,127}$")


class EventType:
    """Standard internal event topics (catalog). Values are stable strings."""

    SIGNAL_ACCEPTED = "signal.accepted"
    SIGNAL_REJECTED = "signal.rejected"
    RISK_DECISION = "risk.decision"
    INTENT_CREATED = "intent.created"
    ORDER_CREATED = "order.created"
    ORDER_STATE_CHANGED = "order.state_changed"
    EXECUTION_SUBMITTED = "execution.submitted"
    EXECUTION_ACKNOWLEDGED = "execution.acknowledged"
    EXECUTION_FILLED = "execution.filled"
    EXECUTION_REJECTED = "execution.rejected"
    EXECUTION_UNKNOWN = "execution.unknown"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"
    PORTFOLIO_SNAPSHOTTED = "portfolio.snapshotted"
    PNL_REALIZED = "pnl.realized"
    RECONCILIATION_DISCREPANCY = "reconciliation.discrepancy"
    RECONCILIATION_COMPLETED = "reconciliation.completed"
    PAPER_RUN_STARTED = "paper.run_started"
    PAPER_FILL = "paper.fill"
    SYSTEM_HEALTH = "system.health"


class DomainEventError(ValueError):
    """Raised when a domain event fails structural validation."""


# Case-insensitive key fragments that must never appear in an event payload.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "refresh",
    "cookie",
    "session_id",
)


def validate_no_secrets(payload: dict[str, Any]) -> None:
    """Reject obviously-sensitive keys anywhere in the payload (recursively)."""
    for key, value in payload.items():
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            raise DomainEventError(f"payload key {key!r} is sensitive and not allowed in events")
        if isinstance(value, dict):
            validate_no_secrets(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    validate_no_secrets(item)


def _require_tz(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DomainEventError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class DomainEvent:
    """An immutable, validated internal domain event."""

    event_type: str
    occurred_at: datetime
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    domain_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not _SAFE_EVENT_TYPE.match(self.event_type):
            raise DomainEventError(
                "event_type must be a lowercase dotted string matching [a-z][a-z0-9_.]*"
            )
        _require_tz(self.occurred_at, "occurred_at")
        if not isinstance(self.source, str) or not self.source.strip():
            raise DomainEventError("source must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise DomainEventError("payload must be a dict")
        validate_no_secrets(self.payload)
        if not isinstance(self.domain_ids, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.domain_ids.items()
        ):
            raise DomainEventError("domain_ids must be a str->str dict")
        if self.causation_id is not None and self.causation_id == str(self.event_id):
            raise DomainEventError("causation_id cannot equal event_id (no self-causation)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "trace_id": self.trace_id,
            "domain_ids": dict(self.domain_ids),
            "payload": dict(self.payload),
        }

    def derive(self, *, event_type: str, payload: dict[str, Any] | None = None, **overrides: Any) -> "DomainEvent":
        """Create a causally-linked child event (same correlation + trace)."""
        return DomainEvent(
            event_type=event_type,
            occurred_at=overrides.pop("occurred_at", datetime.now(timezone.utc)),
            source=overrides.pop("source", self.source),
            payload=payload or {},
            correlation_id=overrides.pop("correlation_id", self.correlation_id),
            causation_id=str(self.event_id),
            trace_id=overrides.pop("trace_id", self.trace_id),
            domain_ids=overrides.pop("domain_ids", dict(self.domain_ids)),
            **overrides,
        )


def create_event(
    *,
    event_type: str,
    source: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    domain_ids: dict[str, str] | None = None,
    occurred_at: datetime | None = None,
) -> DomainEvent:
    """Factory: builds a validated event with a fresh id + tz-aware timestamp."""
    return DomainEvent(
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        source=source,
        payload=payload or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
        trace_id=trace_id,
        domain_ids=domain_ids or {},
    )
