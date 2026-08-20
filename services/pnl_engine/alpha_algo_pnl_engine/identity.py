"""Deterministic P&L event identity (Phase 13).

The durable idempotency boundary is ``pnl_events.execution_id`` (unique): one
accounting event per execution identity. ``event_content_hash`` provides
conflict detection — same execution identity with a different payload is a
CONFLICT, never an overwrite.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID


def event_content_hash(
    *,
    execution_id: str,
    event_type: str,
    account_id: UUID,
    strategy_run_id: UUID,
    instrument_id: UUID,
    trading_mode: str,
    side: str,
    quantity: int,
    price: str | None,
    average_cost: str | None,
    gross_pnl: str,
    costs: str,
    net_pnl: str,
    occurred_at: datetime,
) -> str:
    payload = {
        "execution_id": execution_id,
        "event_type": event_type,
        "account_id": str(account_id),
        "strategy_run_id": str(strategy_run_id),
        "instrument_id": str(instrument_id),
        "trading_mode": trading_mode.upper(),
        "side": side,
        "quantity": quantity,
        "price": price,
        "average_cost": average_cost,
        "gross_pnl": gross_pnl,
        "costs": costs,
        "net_pnl": net_pnl,
        "occurred_at": occurred_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def compute_snapshot_key(*, account_id: UUID, trading_mode: str, snapshot_at: datetime) -> str:
    return f"{account_id}:{trading_mode.upper()}:{snapshot_at.isoformat()}"
