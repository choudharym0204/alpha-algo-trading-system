"""Deterministic position + fill identity (Phase 11).

Two distinct identities are defined here:

* ``PositionIdentity`` — the canonical position key. This project keys a
  position by **(strategy_run_id, instrument_id, trading_mode)**, preserving the
  existing ``uq_positions_strategy_run_id_instrument_id_trading_mode`` unique
  constraint (see ``packages/shared/.../db/models/trading.py``). A strategy run
  already scopes account + mode context; ``broker_account_id`` is a recorded
  (nullable) attribute, not a key dimension.

* ``fill_content_hash`` — a SHA-256 over a fill's mutable payload, used to
  detect identity conflicts (same execution identity, different economics).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from alpha_algo_position_engine.contracts import PositionFill, PositionIdentity

#: Canonical string form used to build a stable position key.
def compute_position_key(
    *, strategy_run_id: UUID, instrument_id: UUID, trading_mode: str
) -> str:
    """Deterministic string key for the canonical (strategy_run, instrument, mode)."""
    return f"{strategy_run_id}:{instrument_id}:{trading_mode.upper()}"


def build_position_identity(
    *, strategy_run_id: UUID, instrument_id: UUID, trading_mode: str
) -> PositionIdentity:
    """Build the canonical ``PositionIdentity`` for a fill/read."""
    return PositionIdentity(
        strategy_run_id=strategy_run_id,
        instrument_id=instrument_id,
        trading_mode=trading_mode.upper(),
    )


def fill_content_hash(fill: PositionFill) -> str:
    """SHA-256 over a fill's mutable economics — used for conflict detection.

    Identity fields (execution_id/order_id/account/instrument/mode) are NOT
    hashed here: they define *which* event this is; the hash defines *what* it
    says. Same identity + different hash => CONFLICT.
    """
    payload = {
        "side": fill.side.upper(),
        "quantity": str(fill.quantity),
        "price": str(fill.price),
        "occurred_at": fill.occurred_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def normalize_fill(
    *,
    execution_id: str,
    order_id: UUID,
    account_id: UUID,
    instrument_id: UUID,
    strategy_run_id: UUID | None,
    trading_mode: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    occurred_at: datetime,
    broker_order_id: str | None = None,
    fill_reference: str | None = None,
) -> PositionFill:
    """Build a normalized ``PositionFill`` from an Execution-Engine fill event.

    This is the Execution → Position handoff boundary: it consumes the Phase-9
    ``BrokerOrderEvent`` fill quantity/timestamp plus the resolved order context,
    and produces a broker-independent fill. It never parses broker payloads.

    ``strategy_run_id`` is required for position attribution: a fill whose order
    has no strategy run cannot be attributed to a canonical position and is
    rejected (fail-closed) here.
    """
    from alpha_algo_position_engine.errors import PositionIdentityError

    if strategy_run_id is None:
        raise PositionIdentityError(
            "cannot attribute fill to a position: strategy_run_id is missing"
        )
    return PositionFill(
        execution_id=execution_id,
        order_id=order_id,
        account_id=account_id,
        instrument_id=instrument_id,
        strategy_run_id=strategy_run_id,
        trading_mode=trading_mode,
        side=side,
        quantity=quantity,
        price=price,
        occurred_at=occurred_at,
        broker_order_id=broker_order_id,
        fill_reference=fill_reference,
    )
