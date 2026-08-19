"""Order intents for the backtest simulation engine (P7-002).

An intent is a caller-decided, pre-evaluated order that the engine consumes
and fills deterministically. The engine never creates intents, never
evaluates signals, and never imports strategy code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from alpha_algo_backtest_engine.errors import BacktestEngineError

__all__ = ["IntentSide", "IntentType", "OrderIntent"]


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


class IntentSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class IntentType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    # STOP and STOP_LIMIT are deliberately unrepresentable in v1: an
    # unsupported order type is a type error, not a runtime branch.


@dataclass(frozen=True)
class OrderIntent:
    """A caller-decided order intent evaluated against replayed history.

    Validation is fail-loud at construction: non-Decimal or non-finite
    quantities, non-positive quantities, naive decision times, LIMIT intents
    without a positive limit price, and MARKET intents that carry a limit
    price are all rejected. The engine consumes intents in strictly
    ascending ``decided_at`` order (ties are rejected at engine entry).
    """

    side: IntentSide
    order_type: IntentType
    quantity: Decimal
    decided_at: datetime
    limit_price: Decimal | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, IntentSide):
            raise BacktestEngineError("side must be an IntentSide member")
        if not isinstance(self.order_type, IntentType):
            raise BacktestEngineError("order_type must be an IntentType member")
        if not isinstance(self.quantity, Decimal):
            raise BacktestEngineError("quantity must be a Decimal (int/float/str are rejected, never coerced)")
        if not self.quantity.is_finite():
            raise BacktestEngineError("quantity must be finite")
        if self.quantity <= 0:
            raise BacktestEngineError("quantity must be positive")
        if not _is_timezone_aware(self.decided_at):
            raise BacktestEngineError("decided_at must be timezone-aware")
        if self.order_type is IntentType.LIMIT:
            if self.limit_price is None:
                raise BacktestEngineError("limit orders require a positive limit_price")
            if not isinstance(self.limit_price, Decimal):
                raise BacktestEngineError("limit_price must be a Decimal")
            if not self.limit_price.is_finite():
                raise BacktestEngineError("limit_price must be finite")
            if self.limit_price <= 0:
                raise BacktestEngineError("limit_price must be positive")
        else:
            if self.limit_price is not None:
                raise BacktestEngineError("market orders must not carry a limit_price")
        if self.label is not None and not isinstance(self.label, str):
            raise BacktestEngineError("label must be a string or None")
