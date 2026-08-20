"""Deterministic execution identity (Phase 9).

An execution request is NOT identified by a random UUID alone. Identity is
derived from the immutable order so that application retries, process restarts,
network timeouts, and duplicate commands all resolve to the SAME execution
identity — the engine can then detect "this order was already submitted".

Distinct concepts:
* ``execution_id``  - deterministic per-order (stable across retries/restarts).
* ``attempt_id``    - deterministic per (execution, attempt_number); retries
                      advance the attempt number without changing execution_id.
* ``broker_order_id`` - external identity (None until the provider assigns it).
"""

from __future__ import annotations

import hashlib
from uuid import UUID


def compute_execution_id(order_id: UUID, order_identity_key: str | None) -> str:
    """Deterministic execution identity for a given order."""
    payload = f"{order_id}:{order_identity_key or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_attempt_id(execution_id: str, attempt_number: int) -> str:
    """Deterministic per-attempt identity (retries advance attempt_number)."""
    return f"{execution_id}-a{attempt_number}"


def compute_event_identity(event) -> str:
    """Stable execution-event identity for idempotency.

    Prefers an explicit ``source_event_id``/``broker_event_id`` from metadata;
    otherwise falls back to a hash over stable order/event fields.
    """
    import json

    source = event.metadata.get("source_event_id") or event.metadata.get(
        "broker_event_id"
    )
    if source:
        return f"{event.order_id}:{source}"
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


def event_content_hash(event) -> str:
    """Hash of an event's mutable payload — used to detect identity conflicts."""
    import json

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
