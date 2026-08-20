"""Phase 14 — boundary adapters (normalized observation, no broker SDK).

Convert Phase-11 position snapshots and Phase-10 funds/position read models into
the Reconciliation Engine's normalized observation types. Provider-specific
parsing stays in the broker adapter; reconciliation consumes only these types.
"""

from __future__ import annotations

from decimal import Decimal

from alpha_algo_reconciliation_engine.contracts import (
    FundsObservation,
    PositionObservation,
)


def position_observation_from_internal(snap) -> PositionObservation:
    """Phase-11 ``PositionSnapshot`` -> normalized internal position observation."""
    return PositionObservation(
        source="internal",
        account_id=getattr(snap, "account_id", None),
        instrument_id=snap.instrument_id,
        quantity=snap.quantity,
        side=(snap.side.value if getattr(snap, "side", None) and hasattr(snap.side, "value") else "LONG"),
        average_price=snap.average_price,
    )


def position_observation_from_broker(snap) -> PositionObservation:
    """Phase-10 ``BrokerPositionSnapshot`` -> normalized broker position observation."""
    qty = int(snap.quantity)
    return PositionObservation(
        source="broker",
        account_id=snap.broker_account_id,
        instrument_id=snap.instrument_id,
        quantity=qty,
        side="LONG" if qty >= 0 else "SHORT",
        average_price=snap.average_price,
        observed_at=getattr(snap, "captured_at", None),
    )


def funds_observation_from_internal(funds) -> FundsObservation | None:
    if funds is None:
        return None
    return FundsObservation(
        source="internal",
        account_id=getattr(funds, "account_id", None),
        available_cash=getattr(funds, "available_cash", None),
        available_margin=getattr(funds, "available_margin", None),
        used_margin=getattr(funds, "used_margin", None),
        currency=getattr(funds, "currency", "INR"),
    )


def funds_observation_from_broker(snap) -> FundsObservation:
    """Phase-10 ``BrokerFundsSnapshot`` -> normalized broker funds observation."""
    return FundsObservation(
        source="broker",
        account_id=snap.broker_account_id,
        available_cash=snap.available_cash,
        available_margin=snap.available_margin,
        used_margin=snap.used_margin,
        currency=snap.currency,
        observed_at=snap.captured_at,
    )
