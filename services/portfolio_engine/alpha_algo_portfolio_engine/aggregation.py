"""Pure portfolio aggregation + exposure arithmetic (Phase 12).

All money math uses ``Decimal`` (never uncontrolled binary float). Exposure is
computed from *reference market prices* (current), not average entry price
(average entry is carried through as a Phase-13 P&L input only).

Price freshness is classified FRESH / STALE / MISSING; a missing or stale price
can never silently become a zero market value — it is flagged and excluded from
a total that is explicitly marked DEGRADED / PARTIAL.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from alpha_algo_portfolio_engine.contracts import (
    PortfolioCompleteness,
    PortfolioComputation,
    PortfolioIdentity,
    PortfolioInputs,
    PortfolioStatus,
    PositionExposure,
    ReferencePrice,
    StrategyBreakdown,
)

#: Money rounding quantum matching Numeric(18,4) columns.
MONEY_QUANTUM = Decimal("0.0001")
ROUNDING = ROUND_HALF_EVEN

PRICE_FRESH = "FRESH"
PRICE_STALE = "STALE"
PRICE_MISSING = "MISSING"


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def classify_price(
    *,
    instrument_id,
    prices: dict,
    now: datetime,
    max_age_seconds: int | None,
) -> tuple[ReferencePrice | None, str]:
    """Classify a position's reference price as FRESH / STALE / MISSING.

    ``max_age_seconds=None`` disables staleness checks (every present price is
    fresh). Future-dated prices are treated as STALE (fail-closed: never trust a
    future price as current).
    """
    price = prices.get(instrument_id)
    if price is None:
        return None, PRICE_MISSING
    if max_age_seconds is None:
        return price, PRICE_FRESH
    age = now - price.observed_at
    if age.total_seconds() > max_age_seconds or price.observed_at > now:
        return price, PRICE_STALE
    return price, PRICE_FRESH


def _signed_exposure(quantity: int, price: Decimal) -> Decimal:
    return round_money(Decimal(quantity) * price)


def aggregate_positions(
    *,
    positions: tuple,
    prices: dict,
    now: datetime,
    max_age_seconds: int | None,
) -> tuple[list[PositionExposure], Decimal, Decimal, Decimal, Decimal, Decimal | None, tuple, tuple]:
    """Aggregate open positions into exposure + market value + breakdown.

    Returns (exposures, gross, net, long, short, market_value, missing_ids,
    stale_ids). ``market_value`` is the signed sum of priced positions (None
    only when there are no open positions at all).
    """
    exposures: list[PositionExposure] = []
    gross = Decimal("0")
    net = Decimal("0")
    long = Decimal("0")
    short = Decimal("0")
    missing_ids: list = []
    stale_ids: list = []
    any_priced = False
    open_count = 0

    for pos in positions:
        if not pos.is_open:
            continue
        open_count += 1
        price, state = classify_price(
            instrument_id=pos.instrument_id,
            prices=prices,
            now=now,
            max_age_seconds=max_age_seconds,
        )
        if state == PRICE_MISSING:
            missing_ids.append(pos.instrument_id)
            exposures.append(
                PositionExposure(
                    position_id=pos.position_id,
                    instrument_id=pos.instrument_id,
                    strategy_run_id=pos.strategy_run_id,
                    quantity=pos.quantity,
                    reference_price=None,
                    market_value=None,
                    price_state=state,
                )
            )
            continue
        if state == PRICE_STALE:
            stale_ids.append(pos.instrument_id)
        any_priced = True
        exposure = _signed_exposure(pos.quantity, price.price)
        gross += abs(exposure)
        net += exposure
        if exposure > 0:
            long += exposure
        else:
            short += -exposure
        exposures.append(
            PositionExposure(
                position_id=pos.position_id,
                instrument_id=pos.instrument_id,
                strategy_run_id=pos.strategy_run_id,
                quantity=pos.quantity,
                reference_price=price.price,
                market_value=exposure,
                price_state=state,
            )
        )

    if open_count == 0:
        market_value = Decimal("0")  # no open positions => zero position value (real, known)
    elif any_priced:
        market_value = round_money(net)
    else:
        market_value = None  # open positions but none priced => unavailable, flagged
    return (
        exposures,
        round_money(gross),
        round_money(net),
        round_money(long),
        round_money(short),
        market_value,
        tuple(missing_ids),
        tuple(stale_ids),
    )


def strategy_breakdown(
    exposures: list[PositionExposure],
) -> tuple[StrategyBreakdown, ...]:
    """Deterministic strategy-level aggregation from per-position exposures."""
    buckets: dict = {}
    for e in exposures:
        b = buckets.setdefault(e.strategy_run_id, {"count": 0, "gross": Decimal("0"), "priced": True})
        b["count"] += 1
        if e.market_value is not None:
            b["gross"] += abs(e.market_value)
        else:
            b["priced"] = False
    out = []
    for sid in sorted(buckets, key=str):
        b = buckets[sid]
        out.append(
            StrategyBreakdown(
                strategy_run_id=sid,
                position_count=b["count"],
                market_value=round_money(b["gross"]) if b["priced"] else None,
                gross_exposure=round_money(b["gross"]),
            )
        )
    return tuple(out)


def compute_portfolio(
    *,
    inputs: PortfolioInputs,
    now: datetime,
    max_age_seconds: int | None = None,
) -> PortfolioComputation:
    """Deterministically compute portfolio state from an input bundle.

    Pure function: no DB, no wall-clock randomness, no unordered iteration.
    """
    identity = PortfolioIdentity(
        account_id=inputs.account_id, trading_mode=inputs.trading_mode.upper()
    )

    (
        exposures,
        gross,
        net,
        long,
        short,
        market_value,
        missing_ids,
        stale_ids,
    ) = aggregate_positions(
        positions=inputs.positions,
        prices=inputs.prices,
        now=now,
        max_age_seconds=max_age_seconds,
    )

    funds = inputs.funds
    funds_available = funds is not None and funds.available_cash is not None
    cash_balance = funds.available_cash if funds_available else None
    available_margin = funds.available_margin if funds is not None else None
    used_margin = funds.used_margin if funds is not None else None

    position_count = sum(1 for p in inputs.positions if p.is_open)

    has_missing = bool(missing_ids)
    has_stale = bool(stale_ids)
    completeness = (
        PortfolioCompleteness.COMPLETE
        if (not has_missing and funds_available)
        else PortfolioCompleteness.PARTIAL
    )
    status = (
        PortfolioStatus.READY
        if (not has_missing and not has_stale and funds_available)
        else PortfolioStatus.DEGRADED
    )

    equity_value = None
    if completeness == PortfolioCompleteness.COMPLETE and market_value is not None:
        equity_value = round_money(cash_balance + market_value)

    return PortfolioComputation(
        identity=identity,
        status=status,
        completeness=completeness,
        position_count=position_count,
        gross_exposure=gross,
        net_exposure=net,
        long_exposure=long,
        short_exposure=short,
        market_value=market_value,
        cash_balance=cash_balance,
        equity_value=equity_value,
        available_margin=available_margin,
        used_margin=used_margin,
        funds_available=funds_available,
        missing_instrument_ids=missing_ids,
        stale_instrument_ids=stale_ids,
        positions=tuple(exposures),
        strategy_breakdown=strategy_breakdown(exposures),
        snapshot_at=now,
    )
