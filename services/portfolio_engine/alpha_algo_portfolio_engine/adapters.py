"""Phase 12 — boundary adapters (normalized input, no broker SDK).

Convert Phase-11 position snapshots and Phase-10 funds snapshots into the
Portfolio Engine's normalized input types. These are the only places that touch
upstream contract types; they never call a broker and never parse broker payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime

from alpha_algo_portfolio_engine.contracts import FundsState, PositionInput


def position_input_from_snapshot(snap) -> PositionInput:
    """Phase-11 ``PositionSnapshot`` -> normalized ``PositionInput``."""
    return PositionInput(
        position_id=snap.position_id,
        instrument_id=snap.instrument_id,
        strategy_run_id=snap.strategy_run_id,
        quantity=snap.quantity,
        average_price=snap.average_price,
        status=snap.status.value if hasattr(snap.status, "value") else str(snap.status),
    )


def funds_from_broker_snapshot(snap) -> FundsState:
    """Phase-10 ``BrokerFundsSnapshot`` -> normalized ``FundsState``.

    Unavailable funds stay ``None`` (never fabricated as zero).
    """
    return FundsState(
        available_cash=snap.available_cash,
        available_margin=snap.available_margin,
        used_margin=snap.used_margin,
        captured_at=snap.captured_at,
    )
