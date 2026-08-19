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
    UnfilledReason,
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


def run(
    *intents: OrderIntent,
    commission: str = "0",
    slippage: str = "0",
    capital: str = "100000",
) -> object:
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
        tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        tick(utc(2026, 1, 1, 9, 2), "110", "109.5", "110.5"),
        tick(utc(2026, 1, 1, 9, 3), "105", "104.5", "105.5"),
    )
    return run_backtest(
        inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
        intents=tuple(intents),
        cost_model=CostModel(commission_per_fill=Decimal(commission), slippage_bps=Decimal(slippage)),
        initial_capital=Decimal(capital),
    )


class TestSlippage:
    def test_buy_pays_worse_price(self) -> None:
        # BUY decided between rec0 and rec1 => fills at rec1 ask 101.5, +10bps.
        result = run(order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)), slippage="10")
        (fill,) = result.fills
        assert fill.anchor_price == Decimal("101.5")
        assert fill.fill_price == Decimal("101.6015")
        assert fill.slippage_per_share == Decimal("0.1015")

    def test_sell_receives_worse_price(self) -> None:
        # BUY first at rec1, then SELL decided between rec1 and rec2 => fills at
        # rec2 bid 109.5, -10bps.
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            slippage="10",
        )
        fills = result.fills
        assert fills[0].fill_price == Decimal("101.6015")  # 101.5 * 1.001
        assert fills[1].fill_price == Decimal("109.3905")  # 109.5 * 0.999
        assert fills[1].slippage_per_share == Decimal("0.1095")

    def test_zero_bps_is_identity(self) -> None:
        result = run(order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)), slippage="0")
        (fill,) = result.fills
        assert fill.fill_price == fill.anchor_price == Decimal("101.5")
        assert fill.slippage_per_share == Decimal("0")

    def test_limit_fill_is_never_slippaged(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="102"),
            slippage="500",
        )
        (fill,) = result.fills
        assert fill.fill_price == Decimal("101.5")
        assert fill.slippage_per_share == Decimal("0")

    def test_total_slippage_cost_is_auditable(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            slippage="10",
        )
        expected = Decimal("0.1015") * Decimal("10") + Decimal("0.1095") * Decimal("10")
        assert result.total_slippage_cost == expected


class TestCommission:
    def test_flat_commission_on_both_sides(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            commission="5",
        )
        fills = result.fills
        assert [f.commission_amount for f in fills] == [Decimal("5"), Decimal("5")]
        assert result.total_commission == Decimal("10")

    def test_buy_cash_flow_negative_includes_commission(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)),
            commission="5",
        )
        (fill,) = result.fills
        # gross = 10 * 101.5 = 1015; cash_flow = -(1015 + 5)
        assert fill.gross_value == Decimal("1015")
        assert fill.cash_flow == Decimal("-1020")

    def test_sell_cash_flow_positive_minus_commission(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            commission="5",
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        # gross = 10 * 109.5 = 1095; cash_flow = 1095 - 5
        assert sell_fill.cash_flow == Decimal("1090")

    def test_unfilled_intents_pay_nothing(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="50"),
            commission="5",
        )
        assert result.fills == ()
        assert result.total_commission == Decimal("0")
        assert result.total_slippage_cost == Decimal("0")

    def test_zero_cost_run_is_explicit_and_valid(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            commission="0",
            slippage="0",
        )
        assert result.total_commission == Decimal("0")
        assert result.total_slippage_cost == Decimal("0")
        assert all(f.fill_price == f.anchor_price for f in result.fills)


class TestCashAccounting:
    def test_buy_beyond_cash_is_rejected_no_margin(self) -> None:
        # 100 shares at ~101.5 = 10150, within 100000; use a tiny capital so
        # the buy cannot be covered.
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), quantity="100"),
            commission="5",
            capital="1000",
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.INSUFFICIENT_CASH.value
        assert result.fills == ()

    def test_sell_whose_commission_drives_cash_negative_is_rejected(self) -> None:
        # Capital 5000, commission 3000: BUY 5 @101.5 costs 3507.5 (cash 1492.5),
        # then SELL 5 @109.5 nets 547.5 - 3000 = -2452.5 which would drive cash
        # to -960 -> rejected (cash-account invariant, no margin).
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="5"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30), quantity="5"),
            commission="3000",
            capital="5000",
        )
        outcomes = result.outcomes
        assert outcomes[0].filled
        assert not outcomes[1].filled
        assert outcomes[1].reason == UnfilledReason.INSUFFICIENT_CASH.value

    def test_cash_never_goes_negative_across_a_full_round_trip(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20), quantity="50"),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30), quantity="50"),
            commission="5",
        )
        assert len(result.fills) == 2
        assert result.final_equity > 0
