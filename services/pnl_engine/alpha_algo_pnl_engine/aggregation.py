"""Deterministic P&L aggregation (Phase 13).

Every higher-level total is the **sum of lower-level accounting facts**, never an
independent recalculation of the same charge. Realized facts come from the
append-only ``pnl_events``; unrealized is passed in separately (mark-to-market).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from alpha_algo_pnl_engine.accounting import round_money
from alpha_algo_pnl_engine.contracts import AggregatedPnl, PnlEvent, PnlEventType


def _sum_realized(events) -> AggregatedPnl:
    gross = Decimal("0")
    costs = Decimal("0")
    net = Decimal("0")
    count = 0
    for e in events:
        if e.event_type != PnlEventType.REALIZED_PNL:
            continue
        gross += e.gross_pnl
        costs += e.costs
        net += e.net_pnl
        count += 1
    return AggregatedPnl(
        key="",
        realized_gross=round_money(gross),
        realized_costs=round_money(costs),
        realized_net=round_money(net),
        trade_count=count,
    )


def aggregate_realized(events, *, key_fn) -> tuple[AggregatedPnl, ...]:
    """Group realized events by an arbitrary key and sum their facts."""
    buckets: dict[str, list[PnlEvent]] = {}
    for e in events:
        buckets.setdefault(key_fn(e), []).append(e)
    out = []
    for key in sorted(buckets):
        agg = _sum_realized(buckets[key])
        out.append(
            AggregatedPnl(
                key=key,
                realized_gross=agg.realized_gross,
                realized_costs=agg.realized_costs,
                realized_net=agg.realized_net,
                trade_count=agg.trade_count,
            )
        )
    return tuple(out)


def strategy_aggregation(events) -> tuple[AggregatedPnl, ...]:
    return aggregate_realized(events, key_fn=lambda e: str(e.strategy_run_id))


def account_aggregation(events) -> tuple[AggregatedPnl, ...]:
    return aggregate_realized(events, key_fn=lambda e: str(e.account_id))


def daily_aggregation(events, *, tz: timezone) -> tuple[AggregatedPnl, ...]:
    """Bucket realized events by local trading day (timezone is configurable)."""

    def day_key(e: PnlEvent) -> str:
        local = e.occurred_at.astimezone(tz)
        return local.date().isoformat()

    return aggregate_realized(events, key_fn=day_key)


def combine_unrealized(
    agg: AggregatedPnl, unrealized: Decimal | None
) -> AggregatedPnl:
    """Attach mark-to-market unrealized P&L to a realized aggregation bucket."""
    u = round_money(unrealized) if unrealized is not None else None
    gross = agg.realized_gross + (u or Decimal("0"))
    net = agg.realized_net + (u or Decimal("0"))
    return AggregatedPnl(
        key=agg.key,
        realized_gross=agg.realized_gross,
        realized_costs=agg.realized_costs,
        realized_net=agg.realized_net,
        unrealized_pnl=u,
        gross_pnl=round_money(gross),
        net_pnl=round_money(net),
        trade_count=agg.trade_count,
    )
