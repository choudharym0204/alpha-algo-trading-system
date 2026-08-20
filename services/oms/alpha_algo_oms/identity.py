"""Deterministic, collision-safe order identity (Phase 8).

An order is traceable to its full provenance (orchestration, signal, strategy,
account, instrument, side, quantity, order type, mode, risk approval) and is
*not* identified by a random UUID alone. Two identities are derived here:

* ``order_identity_key`` - a stable SHA-256 over the immutable intent payload;
  used as the durable idempotency/conflict backstop (unique in ``orders``).
* ``client_order_id`` - a deterministic, human-traceable external identifier
  derived from ``orchestration_id`` (also unique in ``orders``).

The ``internal_order_id`` is the database primary key (a UUID); the broker order
id remains a placeholder (``None``) until Phase 9 execution assigns one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from alpha_algo_trading_engine.intent import TradingIntent


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_order_identity_key(
    *,
    orchestration_id: str,
    signal_id: UUID,
    strategy_id: UUID,
    account_id: UUID | None,
    instrument_id: UUID,
    side: str,
    quantity: int,
    order_type: str,
    trading_mode: str,
    risk_approval_id: str,
) -> str:
    """Deterministic identity hash over the immutable order-intent payload."""
    payload = {
        "orchestration_id": orchestration_id,
        "signal_id": str(signal_id),
        "strategy_id": str(strategy_id),
        "account_id": str(account_id) if account_id is not None else None,
        "instrument_id": str(instrument_id),
        "side": side.upper(),
        "quantity": quantity,
        "order_type": order_type.upper(),
        "trading_mode": trading_mode.upper(),
        "risk_approval_id": risk_approval_id,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def make_client_order_id(orchestration_id: str) -> str:
    """Deterministic, externally-traceable client order id."""
    return f"ord-{orchestration_id}"


@dataclass(frozen=True)
class OrderIdentity:
    """The complete, immutable identity of a created internal order."""

    internal_order_id: UUID
    client_order_id: str
    correlation_id: str | None
    order_identity_key: str
    broker_order_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def build_order_identity(
    intent: TradingIntent,
    *,
    internal_order_id: UUID,
    quantity: int,
) -> OrderIdentity:
    """Build the full order identity for a validated intent."""
    identity_key = compute_order_identity_key(
        orchestration_id=intent.orchestration_id,
        signal_id=intent.signal_id,
        strategy_id=intent.strategy_id,
        account_id=intent.account_id,
        instrument_id=intent.instrument_id,
        side=intent.action,
        quantity=quantity,
        order_type=intent.order_type,
        trading_mode=intent.trading_mode,
        risk_approval_id=str(intent.approval_id),
    )
    return OrderIdentity(
        internal_order_id=internal_order_id,
        client_order_id=make_client_order_id(intent.orchestration_id),
        correlation_id=str(intent.correlation_id),
        order_identity_key=identity_key,
    )
