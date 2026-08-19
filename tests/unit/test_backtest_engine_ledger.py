from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(ts: datetime, ltp: str, bid: str | None = None, ask: str | None = None) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def order(
    side: IntentSide,
    order_type: IntentType,
    decided_at: datetime,
    quantity: str = "10",
    limit_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        decided_at=decided_at,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


def run(*intents: OrderIntent, commission: str = "0", slippage: str = "0") -> object:
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
        tick(utc(2026, 1, 1, 9, 1), "102", "101.5", "102.5"),
        tick(utc(2026, 1, 1, 9, 2), "104", "103.5", "104.5"),
        tick(utc(2026, 1, 1, 9, 3), "106", "105.5", "106.5"),
    )
    return run_backtest(
        inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
        intents=tuple(intents),
        cost_model=CostModel(commission_per_fill=Decimal(commission), slippage_bps=Decimal(slippage)),
        initial_capital=Decimal("100000"),
    )


class TestFifoLots:
    def test_single_round_trip_produces_one_trade(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            commission="5",
        )
        assert len(result.trades) == 1
        (trade,) = result.trades
        assert trade.entry_price == Decimal("102.5")
        assert trade.exit_price == Decimal("103.5")
        # (103.5 - 102.5) * 10 - 5 - 5 = 10 - 10 = 0
        assert trade.realized_pnl == Decimal("0")

    def test_two_entries_one_exit_produces_two_fifo_trades(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 20), quantity="10"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), quantity="20"),
            commission="5",
        )
        trades = result.trades
        assert len(trades) == 2
        assert trades[0].entry_price == Decimal("102.5")  # first buy at rec1 ask
        assert trades[1].entry_price == Decimal("104.5")  # second buy at rec2 ask
        assert trades[0].quantity == Decimal("10")
        assert trades[1].quantity == Decimal("10")

    def test_partial_exit_leaves_lot_open_then_completes(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30), quantity="4"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), quantity="6"),
            commission="5",
        )
        assert len(result.fills) == 3
        assert len(result.trades) == 1
        (trade,) = result.trades
        assert trade.quantity == Decimal("10")
        # weighted exit: (4*103.5 + 6*105.5) / 10 = (414 + 633)/10 = 104.7
        assert trade.exit_price == Decimal("104.7")
        assert trade.exit_fill_sequences == (1, 2)

    def test_partial_exit_split_exit_commission_proportionally(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30), quantity="4"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), quantity="6"),
            commission="10",
        )
        (trade,) = result.trades
        # entry cost 10 (one BUY fill) attributed to the lot; exit cost is the
        # full 10 + 10 from the two SELL fills (proportional split across lots
        # only matters when one SELL consumes multiple lots).
        assert trade.entry_cost == Decimal("10")
        assert trade.exit_cost == Decimal("20")
        assert trade.realized_pnl == Decimal("-8")  # (104.7-102.5)*10 - 10 - 20

    def test_realized_pnl_is_net_of_costs(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30), quantity="10"),
            commission="5",
        )
        (trade,) = result.trades
        assert trade.realized_pnl == (Decimal("103.5") - Decimal("102.5")) * Decimal("10") - Decimal("5") - Decimal("5")

    def test_equity_marks_position_at_every_record(self) -> None:
        # BUY 10 at rec1 (fills at ask 102.5): equity at rec1 = cash + 10*ltp(rec1).
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            commission="5",
        )
        curve = result.equity_curve
        assert len(curve) == 4
        assert curve[0].equity == Decimal("100000")
        # cash after buy = 100000 - 1025 - 5 = 98970; position 10 * ltp 102 = 1020
        assert curve[1].equity == Decimal("99990")
        assert curve[2].equity == Decimal("98970") + Decimal("10") * Decimal("104")
        assert curve[3].equity == Decimal("98970") + Decimal("10") * Decimal("106")

    def test_unfilled_or_rejected_intents_produce_no_trades(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 20), limit_price="50"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
        )
        assert result.fills == ()
        assert result.trades == ()
        assert all(point.equity == Decimal("100000") for point in result.equity_curve)

    def test_one_exit_consuming_two_lots_splits_exit_commission_proportionally(self) -> None:
        # Two BUY lots (10 + 10), one SELL of 20 consuming both lots in FIFO
        # order. Exit commission 10 must split 5/5 across the two trades
        # (qty-proportional), not 10/0 or 10/10.
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="10"),
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 20), quantity="10"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), quantity="20"),
            commission="10",
        )
        trades = result.trades
        assert len(trades) == 2
        assert trades[0].quantity == Decimal("10")
        assert trades[1].quantity == Decimal("10")
        # SELL anchors at rec3 (decided 09:02:30 -> next record 09:03) bid 105.5.
        assert trades[0].exit_price == Decimal("105.5")
        assert trades[1].exit_price == Decimal("105.5")
        # one SELL fill with commission 10, split proportionally by quantity
        # consumed from each lot (10/20 and 10/20) => 5 and 5.
        assert trades[0].exit_cost == Decimal("5")
        assert trades[1].exit_cost == Decimal("5")
        # entry costs: 10 each (one BUY fill per lot).
        assert trades[0].entry_cost == Decimal("10")
        assert trades[1].entry_cost == Decimal("10")
        # realized: lot0 (105.5-102.5)*10 -10 -5 = 30-15 = 15; lot1 (105.5-104.5)*10 -10 -5 = -5
        assert trades[0].realized_pnl == Decimal("15")
        assert trades[1].realized_pnl == Decimal("-5")
        # sum of realized P&L equals final-equity delta (no hidden costs):
        # 100000 + 10 = 100010; equity at last record = cash + 0 position = 100010
        assert result.final_equity == Decimal("100010")
