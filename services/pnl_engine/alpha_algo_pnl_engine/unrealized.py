"""Mark-to-market unrealized P&L with price freshness (Phase 13).

Mirrors Phase 3/12 freshness semantics: a missing/stale/future-dated/invalid
reference price can never produce a "current" unrealized P&L — it is flagged
UNAVAILABLE or DEGRADED, never silently trusted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from alpha_algo_pnl_engine.accounting import unrealized_pnl_long
from alpha_algo_pnl_engine.contracts import (
    PnlStatus,
    PriceState,
    UnrealizedPnl,
)


def classify_price(
    *,
    price,
    now: datetime,
    max_age_seconds: int | None,
) -> tuple[Decimal | None, PriceState]:
    """Classify a reference price as FRESH / STALE / MISSING.

    ``max_age_seconds=None`` disables staleness (every present price is fresh).
    Future-dated prices are STALE (fail-closed: never trust a future price).
    Invalid (non-positive) prices are treated as MISSING by the caller.
    """
    if price is None or price.price <= Decimal("0"):
        return None, PriceState.MISSING
    if max_age_seconds is None:
        return price.price, PriceState.FRESH
    if price.observed_at > now:
        return price.price, PriceState.STALE
    if (now - price.observed_at).total_seconds() > max_age_seconds:
        return price.price, PriceState.STALE
    return price.price, PriceState.FRESH


def mark_to_market(
    *,
    quantity: int,
    average_cost: Decimal | None,
    position_id,
    instrument_id,
    price,
    now: datetime,
    max_age_seconds: int | None = None,
) -> UnrealizedPnl:
    """Compute unrealized P&L for an open position (long-only).

    Returns an ``UnrealizedPnl`` whose ``unrealized_pnl`` is ``None`` (and
    status UNAVAILABLE) whenever the reference price is missing/invalid, and
    DEGRADED when stale/future-dated.
    """
    if quantity == 0:
        return UnrealizedPnl(
            position_id=position_id,
            instrument_id=instrument_id,
            quantity=0,
            average_cost=average_cost,
            reference_price=None,
            unrealized_pnl=Decimal("0"),
            price_state=PriceState.FRESH,
            status=PnlStatus.READY,
        )
    if average_cost is None:
        return UnrealizedPnl(
            position_id=position_id,
            instrument_id=instrument_id,
            quantity=quantity,
            average_cost=None,
            reference_price=None,
            unrealized_pnl=None,
            price_state=PriceState.MISSING,
            status=PnlStatus.UNAVAILABLE,
        )
    ref_price, state = classify_price(price=price, now=now, max_age_seconds=max_age_seconds)
    if ref_price is None:
        return UnrealizedPnl(
            position_id=position_id,
            instrument_id=instrument_id,
            quantity=quantity,
            average_cost=average_cost,
            reference_price=None,
            unrealized_pnl=None,
            price_state=PriceState.MISSING,
            status=PnlStatus.UNAVAILABLE,
        )
    u = unrealized_pnl_long(
        reference_price=ref_price, average_cost=average_cost, open_quantity=quantity
    )
    status = PnlStatus.READY if state == PriceState.FRESH else PnlStatus.DEGRADED
    return UnrealizedPnl(
        position_id=position_id,
        instrument_id=instrument_id,
        quantity=quantity,
        average_cost=average_cost,
        reference_price=ref_price,
        unrealized_pnl=u,
        price_state=state,
        status=status,
    )
