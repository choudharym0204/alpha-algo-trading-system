from __future__ import annotations

"""Value types for the paper trading foundation.

Every type here is a frozen dataclass with ``__post_init__`` validation so that
invalid simulation input fails at construction time (mirrors the P7-001
``BacktestInput`` pattern). All prices are ``Decimal``; all timestamps are
timezone-aware UTC.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from alpha_algo_broker_adapters import OrderSide, TradingMode

from alpha_algo_paper_trading.errors import PaperAdapterError

#: Decimal precision used for paper average-price computation.
AVERAGE_PRICE_QUANTUM = Decimal("0.00000001")
#: Rounding mode used for paper average-price computation.
AVERAGE_PRICE_ROUNDING = ROUND_HALF_EVEN

__all__ = [
    "AVERAGE_PRICE_QUANTUM",
    "AVERAGE_PRICE_ROUNDING",
    "FillDecision",
    "PaperFillRecord",
    "PaperPosition",
    "PaperReferencePrice",
    "now_from",
]


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def now_from(clock: Callable[[], datetime]) -> datetime:
    """Read the injected clock and validate its output is timezone-aware.

    The paper foundation never reads the wall clock: every timestamp comes
    from the caller-injected clock. A non-datetime or naive clock output is a
    contract violation and raises ``PaperAdapterError`` immediately
    (ADR-0007).
    """
    value = clock()
    if not isinstance(value, datetime):
        raise PaperAdapterError(
            f"clock must return a datetime, got {type(value).__name__}"
        )
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise PaperAdapterError("clock output must be timezone-aware")
    return value


@dataclass(frozen=True)
class PaperReferencePrice:
    """Caller-owned simulation input used to decide paper fills.

    This is explicitly *not* a market quote: it is an injected, caller-owned
    snapshot that the simulator consumes to produce deterministic fills. It is
    never fetched, never defaulted, and never presented as real market data.
    """

    instrument_id: UUID
    last: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    reference_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)

    def __post_init__(self) -> None:
        if self.last <= Decimal("0"):
            raise ValueError("last must be positive")
        if self.bid is not None and self.bid <= Decimal("0"):
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= Decimal("0"):
            raise ValueError("ask must be positive")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        if (
            self.bid is not None
            and self.ask is not None
            and not (self.bid <= self.last <= self.ask)
        ):
            raise ValueError("last must lie within the bid/ask spread when both legs are present")
        _require_timezone(self.reference_at, "reference_at")


@dataclass(frozen=True)
class FillDecision:
    """Outcome of the pure fill-policy function.

    ``fills=True`` carries the deterministic fill price (> 0) and the full
    order quantity (> 0); ``fills=False`` carries ``None`` price and zero
    quantity. The invariant is enforced in ``__post_init__``.
    """

    fills: bool
    fill_price: Decimal | None
    fill_quantity: Decimal
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.fills:
            if self.fill_price is None or self.fill_price <= Decimal("0"):
                raise ValueError("fill decisions require a positive fill_price")
            if self.fill_quantity <= Decimal("0"):
                raise ValueError("fill decisions require a positive fill_quantity")
        else:
            if self.fill_price is not None:
                raise ValueError("rejection decisions must carry fill_price=None")
            if self.fill_quantity != Decimal("0"):
                raise ValueError("rejection decisions must carry zero fill_quantity")


@dataclass(frozen=True)
class PaperFillRecord:
    """Immutable, append-only book entry for one simulator-confirmed fill."""

    sequence: int
    client_order_id: str
    broker_order_id: str
    order_id: UUID
    side: OrderSide
    instrument_id: UUID
    broker_account_id: UUID
    fill_quantity: Decimal
    fill_price: Decimal
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        if self.fill_quantity <= Decimal("0"):
            raise ValueError("fill_quantity must be positive")
        if self.fill_price <= Decimal("0"):
            raise ValueError("fill_price must be positive")
        _require_timezone(self.occurred_at, "occurred_at")


@dataclass(frozen=True)
class PaperPosition:
    """A PAPER-labeled position derived from simulator-confirmed fills.

    ``trading_mode`` is structurally pinned to ``TradingMode.PAPER``: this type
    refuses to represent any other mode, so a paper ledger can never produce a
    LIVE-tagged record (docs/API.md: "Paper positions and live positions must
    never mix.").
    """

    broker_account_id: UUID
    instrument_id: UUID
    trading_mode: TradingMode
    quantity: Decimal
    average_price: Decimal | None
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.trading_mode is not TradingMode.PAPER:
            raise ValueError(
                f"paper positions must use TradingMode.PAPER, got {self.trading_mode}"
            )
        if self.average_price is not None and self.average_price <= Decimal("0"):
            raise ValueError("average_price must be positive when present")
        _require_timezone(self.captured_at, "captured_at")
