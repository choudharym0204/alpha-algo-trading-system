"""Broker event normalization + deduplication (Phase 10).

Provider event streams (WebSocket / postback) are parsed + validated into
``NormalizedBrokerEvent``, then deduplicated by stable event identity. Duplicate
events are dropped; reuse of an identity with a *different* payload becomes a
conflict (never an overwrite). Provider-specific events never flow into OMS.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class BrokerEventType(StrEnum):
    ORDER_UPDATE = "ORDER_UPDATE"
    TRADE = "TRADE"
    FILL = "FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NormalizedBrokerEvent:
    """A validated, provider-neutral execution event."""

    order_id: UUID
    event_type: BrokerEventType
    broker_order_id: str | None
    fill_quantity: Decimal
    occurred_at: datetime
    reason: str = ""
    source_event_id: str | None = None


def compute_event_identity(event: NormalizedBrokerEvent) -> str:
    """Stable event identity (prefers an explicit provider source id)."""
    if event.source_event_id:
        return f"{event.order_id}:{event.source_event_id}"
    payload = json.dumps(
        {
            "order_id": str(event.order_id),
            "type": event.event_type.value,
            "broker_order_id": event.broker_order_id,
            "fill_quantity": str(event.fill_quantity),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_hash(event: NormalizedBrokerEvent) -> str:
    payload = json.dumps(
        {
            "type": event.event_type.value,
            "broker_order_id": event.broker_order_id,
            "fill_quantity": str(event.fill_quantity),
            "reason": event.reason,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DuplicateEventError(Exception):
    """Same identity, different payload (conflict) — not an overwrite."""


class EventDeduplicator:
    """Dedups events by identity; conflict on same identity + different payload."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}  # identity -> content hash

    def seen(self, event: NormalizedBrokerEvent) -> bool:
        return compute_event_identity(event) in self._seen

    def apply(self, event: NormalizedBrokerEvent) -> bool:
        """Return True if the event is new (record it); raise on conflict."""
        identity = compute_event_identity(event)
        content = _content_hash(event)
        existing = self._seen.get(identity)
        if existing is not None:
            if existing != content:
                raise DuplicateEventError(
                    f"event identity conflict for {identity}"
                )
            return False  # exact duplicate -> no effect
        self._seen[identity] = content
        return True
