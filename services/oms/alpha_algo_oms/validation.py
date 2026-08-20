"""Intent-to-order validation (Phase 8).

Every validation rule is fail-closed. A ``TradingIntent`` is converted into a
concrete, immutable ``OrderSpec`` only after *all* rules pass; if any rule fails
``OrderValidationError`` is raised and NO order is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from alpha_algo_trading_engine.intent import TradingIntent

from alpha_algo_oms.errors import OrderValidationError, TradingModeError

ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})
ALLOWED_ACTIONS = frozenset({"BUY", "SELL", "EXIT"})
ALLOWED_ORDER_TYPES = frozenset({"MARKET", "LIMIT", "STOP", "STOP_LIMIT"})


@dataclass(frozen=True)
class OrderSpec:
    """The validated, immutable order representation handed to persistence."""

    orchestration_id: str
    correlation_id: str | None
    signal_id: UUID
    strategy_id: UUID
    strategy_version: str
    strategy_run_id: UUID | None
    account_id: UUID | None
    instrument_id: UUID
    side: str
    quantity: int
    order_type: str
    limit_price: Decimal | None
    trading_mode: str
    risk_decision_id: UUID
    risk_approval_id: str
    approval_expires_at: datetime
    binding_hash: str
    metadata: dict[str, object]


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise OrderValidationError(f"{field_name} must be timezone-aware")


def _to_quantity(value: Decimal) -> int:
    if value <= Decimal("0"):
        raise OrderValidationError("quantity must be positive")
    if value != value.to_integral_value():
        raise OrderValidationError("quantity must be a whole number")
    return int(value)


def validate_intent(
    intent: TradingIntent,
    *,
    now: datetime | None = None,
    global_halt_active: bool = True,
) -> OrderSpec:
    """Validate a ``TradingIntent`` and return a validated ``OrderSpec``.

    ``global_halt_active`` defaults to True (fail-closed): while the global halt
    is active, order creation is refused. LIVE / unknown trading modes are always
    blocked.
    """
    if intent is None:
        raise OrderValidationError("intent is required")
    if not intent.orchestration_id or not intent.orchestration_id.strip():
        raise OrderValidationError("orchestration_id is required")

    now = now or datetime.now(tz=UTC)

    # Trading mode gate (fail-closed; LIVE/unknown blocked).
    mode = (intent.trading_mode or "").upper()
    if mode == "LIVE":
        raise TradingModeError("LIVE trading is disabled (fail-closed)")
    if mode not in ALLOWED_MODES:
        raise TradingModeError(f"unknown trading mode: {intent.trading_mode}")

    # Global halt gate.
    if global_halt_active:
        raise OrderValidationError(
            "global trading halt is active; order creation refused"
        )

    # Action / order type gates.
    action = (intent.action or "").upper()
    if action not in ALLOWED_ACTIONS:
        raise OrderValidationError(f"unsupported action: {intent.action}")
    order_type = (intent.order_type or "").upper()
    if order_type not in ALLOWED_ORDER_TYPES:
        raise OrderValidationError(f"unsupported order type: {intent.order_type}")

    # Quantity.
    quantity = _to_quantity(intent.quantity)

    # Approval expiry.
    _require_timezone(intent.approval_expires_at, "approval_expires_at")
    if intent.approval_expires_at <= now:
        raise OrderValidationError("risk approval is expired")

    # Identity fields must be present.
    if intent.signal_id is None:
        raise OrderValidationError("signal_id is required")
    if intent.strategy_id is None:
        raise OrderValidationError("strategy_id is required")
    if intent.instrument_id is None:
        raise OrderValidationError("instrument_id is required")
    if intent.approval_id is None:
        raise OrderValidationError("approval_id is required")
    if intent.account_id is None:
        raise OrderValidationError("account_id is required")

    return OrderSpec(
        orchestration_id=intent.orchestration_id,
        correlation_id=str(intent.correlation_id),
        signal_id=intent.signal_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        strategy_run_id=intent.strategy_run_id,
        account_id=intent.account_id,
        instrument_id=intent.instrument_id,
        side=action,
        quantity=quantity,
        order_type=order_type,
        limit_price=intent.limit_price,
        trading_mode=mode,
        risk_decision_id=intent.risk_decision_id,
        risk_approval_id=str(intent.approval_id),
        approval_expires_at=intent.approval_expires_at,
        binding_hash=intent.binding_hash,
        metadata=intent.metadata or {},
    )
