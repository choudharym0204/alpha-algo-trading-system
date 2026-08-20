"""Pure P&L financial arithmetic (Phase 13).

Accounting method: **Weighted Average Cost** (long-only), matching the Phase-11
position engine's cost basis. Realized P&L is computed on the closing (SELL)
fill against the authoritative average cost carried by the position *before*
the sell. Unrealized P&L is mark-to-market.

All money math is exact ``Decimal`` (4-dp half-even, matching Numeric(18,4)).
Quantity is whole-share ``int``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

#: Money rounding quantum matching Numeric(18,4) columns.
MONEY_QUANTUM = Decimal("0.0001")
ROUNDING = ROUND_HALF_EVEN


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def realized_pnl_long(
    *, sell_price: Decimal, average_cost: Decimal, closed_quantity: int
) -> Decimal:
    """Realized gross P&L for a long close under weighted-average cost.

    ``(sell_price - average_cost) * closed_quantity``.
    """
    if closed_quantity <= 0:
        raise ValueError("closed_quantity must be positive")
    return round_money((sell_price - average_cost) * Decimal(closed_quantity))


def net_pnl(*, gross: Decimal, costs: Decimal) -> Decimal:
    """Net P&L = gross P&L - costs."""
    return round_money(gross - costs)


def costs_total(costs: tuple) -> Decimal:
    return round_money(sum((c.amount for c in costs), Decimal("0")))


def unrealized_pnl_long(
    *, reference_price: Decimal, average_cost: Decimal, open_quantity: int
) -> Decimal:
    """Mark-to-market unrealized P&L for an open long position.

    ``(reference_price - average_cost) * open_quantity``.
    """
    if open_quantity <= 0:
        raise ValueError("open_quantity must be positive")
    return round_money((reference_price - average_cost) * Decimal(open_quantity))
