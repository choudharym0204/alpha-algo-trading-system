"""Deterministic reconciliation identity (Phase 14).

A discrepancy's **identity** is `(account_id, entity_type, entity_id, kind)` —
re-running the same observation yields the same key, so no duplicate
discrepancies are created. Its **content hash** detects conflicting evidence for
the same identity (CONFLICT, never an overwrite).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID


def compute_discrepancy_key(
    *,
    account_id: UUID,
    entity_type: str,
    entity_id: str,
    kind: str,
) -> str:
    payload = {
        "account_id": str(account_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "kind": kind,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def discrepancy_content_hash(
    *,
    internal_state: dict,
    broker_state: dict,
    observed_at: datetime | None,
) -> str:
    payload = {
        "internal_state": _jsonable(internal_state),
        "broker_state": _jsonable(broker_state),
        "observed_at": observed_at.isoformat() if observed_at else None,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    return value
