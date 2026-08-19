from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    CostModel,
    EquityPoint,
    IntentSide,
    IntentType,
    OrderIntent,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput, BacktestTradingMode

from alpha_algo_backtest_reports import BacktestReport, build_report

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(ts: datetime, ltp: str) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def order(side: IntentSide, decided_at: datetime, quantity: str = "10") -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=IntentType.MARKET,
        quantity=Decimal(quantity),
        decided_at=decided_at,
    )


def run_fixture(records: tuple[MarketTick, ...], intents: tuple[OrderIntent, ...], commission: str, slippage: str) -> object:
    return run_backtest(
        inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
        intents=intents,
        cost_model=CostModel(commission_per_fill=Decimal(commission), slippage_bps=Decimal(slippage)),
        initial_capital=Decimal("100000"),
    )


def fixture_a() -> object:
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100"),
        tick(utc(2026, 1, 1, 9, 1), "100"),
        tick(utc(2026, 1, 1, 9, 2), "101"),
        tick(utc(2026, 1, 1, 9, 3), "100"),
        tick(utc(2026, 1, 1, 9, 4), "99.6"),
        tick(utc(2026, 1, 1, 9, 5), "100"),
        tick(utc(2026, 1, 1, 9, 6), "100.2"),
        tick(utc(2026, 1, 1, 9, 7), "100.2"),
    )
    intents = (
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 0, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 1, 30)),
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 2, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 3, 30)),
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 4, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 5, 30)),
    )
    return run_fixture(records, intents, "0", "0")


def fixture_b() -> object:
    """Multi-exit partial fill: one trade closed by two SELL fills."""
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100"),
        tick(utc(2026, 1, 1, 9, 1), "100"),
        tick(utc(2026, 1, 1, 9, 2), "105"),
        tick(utc(2026, 1, 1, 9, 3), "110"),
        tick(utc(2026, 1, 1, 9, 4), "110"),
    )
    intents = (
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 0, 30), quantity="20"),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 1, 30), quantity="12"),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 2, 30), quantity="8"),
    )
    return run_fixture(records, intents, "0", "0")


def fixture_c() -> object:
    """Single trade with fees + slippage."""
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100"),
        tick(utc(2026, 1, 1, 9, 1), "100"),
        tick(utc(2026, 1, 1, 9, 2), "105"),
        tick(utc(2026, 1, 1, 9, 3), "105"),
    )
    intents = (
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 0, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 1, 30)),
    )
    return run_fixture(records, intents, "5", "100")


class TestReportAssembly:
    def test_returns_backtest_report_and_frozen(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert isinstance(report, BacktestReport)
        with pytest.raises(Exception):
            report.initial_capital = Decimal("1")  # type: ignore[misc]

    def test_echoes_inputs(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0.005"))
        assert report.initial_capital == Decimal("100000")
        assert report.risk_free_rate_per_period == Decimal("0.005")
        assert report.mode is BacktestTradingMode.BACKTEST

    def test_echoes_base_metrics(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.metrics.final_equity == Decimal("100008")
        assert report.metrics.total_return == Decimal("8") / Decimal("100000")
        assert report.metrics.trade_count == 3

    def test_trade_count_matches(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert len(report.trades) == 3

    def test_buckets_present(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.daily_buckets
        assert report.monthly_buckets
        assert report.yearly_buckets

    def test_limitations_present(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.limitations
        assert any("single-instrument" in item for item in report.limitations)


class TestReconstruction:
    def test_trade_1(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        trade = report.trades[0]
        assert trade.trade_id == 0
        assert trade.side == "long"
        assert trade.entry_timestamp == utc(2026, 1, 1, 9, 1)
        assert trade.entry_price == Decimal("100")
        assert trade.exit_timestamp == utc(2026, 1, 1, 9, 2)
        assert trade.exit_price == Decimal("101")
        assert trade.quantity == Decimal("10")
        assert trade.gross_pnl == Decimal("10")
        assert trade.net_pnl == Decimal("10")
        assert trade.fees == Decimal("0")

    def test_losing_trade(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        trade = report.trades[1]
        assert trade.gross_pnl == Decimal("-4")
        assert trade.net_pnl == Decimal("-4")

    def test_honest_none_fields(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        for trade in report.trades:
            assert trade.mfe is None
            assert trade.mae is None
            assert trade.entry_reason is None
            assert trade.exit_reason is None
            assert trade.stop_loss is None
            assert trade.target is None

    def test_fees_and_slippage_reconciliation(self) -> None:
        report = build_report(fixture_c(), risk_free_rate_per_period=Decimal("0"))
        trade = report.trades[0]
        assert trade.fees == Decimal("10")
        assert trade.net_pnl == Decimal("19.5")
        assert trade.gross_pnl == Decimal("29.5")
        assert trade.net_pnl == trade.gross_pnl - trade.fees
        assert trade.slippage == Decimal("20.5")

    def test_multi_exit_single_record_weighted_exit(self) -> None:
        report = build_report(fixture_b(), risk_free_rate_per_period=Decimal("0"))
        assert len(report.trades) == 1
        trade = report.trades[0]
        assert trade.exit_price == Decimal("107")
        assert trade.exit_timestamp == utc(2026, 1, 1, 9, 3)
        assert trade.net_pnl == Decimal("140")


class TestEmptyReport:
    def test_empty_report_mostly_none(self) -> None:
        records = (tick(utc(2026, 1, 1, 9, 0), "100"),)
        run = run_fixture(records, (), "0", "0")
        report = build_report(run, risk_free_rate_per_period=Decimal("0"))
        assert report.metrics.trade_count == 0
        assert report.trades == ()
        assert report.statistics.net_profit == Decimal("0")
        assert report.statistics.expectancy is None
