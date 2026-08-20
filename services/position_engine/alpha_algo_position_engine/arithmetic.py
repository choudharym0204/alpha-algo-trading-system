"""Pure financial arithmetic for the Position Engine (Phase 11).

All money math uses ``Decimal`` (never uncontrolled binary float). Quantity is
whole-share ``int``. The engine is **LONG-only** in this phase: ``BUY``
increases long exposure, ``SELL`` decreases it down to (and including) zero,
and any SELL that would go negative is rejected (no short, no flip).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from alpha_algo_position_engine.contracts import PositionStatus

#: Price rounding quantum matching the ``positions.average_price`` Numeric(18,4).
PRICE_QUANTUM = Decimal("0.0001")
PRICE_ROUNDING = ROUND_HALF_EVEN


def round_price(value: Decimal) -> Decimal:
    """Round a price to the persisted quantum (4 dp, half-even)."""
    return value.quantize(PRICE_QUANTUM, rounding=PRICE_ROUNDING)


def weighted_average(
    *,
    previous_quantity: int,
    previous_average: Decimal | None,
    fill_quantity: int,
    fill_price: Decimal,
) -> Decimal:
    """Weighted average entry for same-direction accumulation.

    ``(previous_qty * previous_avg + fill_qty * fill_price) / (previous_qty + fill_qty)``
    using exact Decimal arithmetic, rounded to the price quantum.
    """
    if fill_quantity <= 0:
        raise ValueError("fill_quantity must be positive")
    prev_q = previous_quantity
    if prev_q == 0 or previous_average is None:
        return round_price(fill_price)
    total_notional = (
        Decimal(prev_q) * previous_average + Decimal(fill_quantity) * fill_price
    )
    return round_price(total_notional / Decimal(prev_q + fill_quantity))


@dataclass(frozen=True)
class PositionDelta:
    """The deterministic result of applying one fill to a position."""

    quantity: int
    average_price: Decimal | None
    status: PositionStatus
    opened_at: datetime | None
    closed_at: datetime | None
    event_type: str
    side: str


def apply_buy(
    *,
    quantity: int,
    average_price: Decimal | None,
    opened_at: datetime | None,
    closed_at: datetime | None,
    fill_quantity: int,
    fill_price: Decimal,
    occurred_at: datetime,
) -> PositionDelta:
    """Apply a BUY fill (opens or increases a long position)."""
    if fill_quantity <= 0:
        raise ValueError("fill_quantity must be positive")
    was_flat = quantity == 0
    next_quantity = quantity + fill_quantity
    next_average = weighted_average(
        previous_quantity=quantity,
        previous_average=average_price,
        fill_quantity=fill_quantity,
        fill_price=fill_price,
    )
    event_type = "POSITION_OPENED" if was_flat else "POSITION_INCREASED"
    return PositionDelta(
        quantity=next_quantity,
        average_price=next_average,
        status=PositionStatus.OPEN,
        opened_at=occurred_at if was_flat else opened_at,
        closed_at=None,
        event_type=event_type,
        side="LONG",
    )


def apply_sell(
    *,
    quantity: int,
    average_price: Decimal | None,
    opened_at: datetime | None,
    closed_at: datetime | None,
    fill_quantity: int,
    fill_price: Decimal,
    occurred_at: datetime,
) -> PositionDelta:
    """Apply a SELL fill (decreases or closes a long position).

    Long-only: ``fill_quantity`` must not exceed the current quantity. A SELL on
    a flat position (or exceeding it) is rejected by the caller as over-close /
    unsupported-short.
    """
    if fill_quantity <= 0:
        raise ValueError("fill_quantity must be positive")
    if fill_quantity > quantity:
        raise ValueError("SELL fill exceeds open long quantity (over-close)")
    next_quantity = quantity - fill_quantity
    if next_quantity == 0:
        return PositionDelta(
            quantity=0,
            average_price=None,
            status=PositionStatus.CLOSED,
            opened_at=opened_at,
            closed_at=occurred_at,
            event_type="POSITION_CLOSED",
            side="LONG",
        )
    # Partial close: average entry of remaining shares is unchanged.
    return PositionDelta(
        quantity=next_quantity,
        average_price=average_price,
        status=PositionStatus.OPEN,
        opened_at=opened_at,
        closed_at=None,
        event_type="POSITION_DECREASED",
        side="LONG",
    )
