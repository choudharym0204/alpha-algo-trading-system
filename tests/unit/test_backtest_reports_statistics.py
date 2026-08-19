from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    BacktestRun,
    CostModel,
    EquityPoint,
    FillOutcome,
    FillRecord,
    IntentSide,
    IntentType,
    OrderIntent,
    TradeRecord,
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


def make_trade(seq: int, pnl: str, entry_seq: int | None = None, exit_seqs: tuple[int, ...] | None = None) -> TradeRecord:
    entry_seq = 2 * seq if entry_seq is None else entry_seq
    exit_seqs = (2 * seq + 1,) if exit_seqs is None else exit_seqs
    return TradeRecord(
        sequence=seq,
        entry_fill_sequence=entry_seq,
        exit_fill_sequences=exit_seqs,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        exit_price=Decimal("100") + Decimal(pnl),
        entry_cost=Decimal("0"),
        exit_cost=Decimal("0"),
        realized_pnl=Decimal(pnl),
    )


def make_run(
    trades: tuple[TradeRecord, ...],
    *,
    curve: tuple[EquityPoint, ...] | None = None,
    fill_times: dict[int, datetime] | None = None,
) -> object:
    fill_times = fill_times or {}
    seqs: set[int] = set()
    for trade in trades:
        seqs.add(trade.entry_fill_sequence)
        seqs.update(trade.exit_fill_sequences)
    fills: list[FillRecord] = []
    intents: list[OrderIntent] = []
    outcomes: list[FillOutcome] = []
    for index, seq in enumerate(sorted(seqs)):
        ts = fill_times.get(seq, utc(2026, 1, 1, 9, 0, index))
        side = IntentSide.BUY if seq % 2 == 0 else IntentSide.SELL
        quantity = Decimal("1")
        fill = FillRecord(
            sequence=seq,
            intent_index=index,
            side=side,
            quantity=quantity,
            anchor_price=Decimal("100"),
            slippage_per_share=Decimal("0"),
            fill_price=Decimal("100"),
            commission_amount=Decimal("0"),
            gross_value=quantity * Decimal("100"),
            cash_flow=Decimal("0"),
            record_index=0,
            filled_at=ts,
        )
        fills.append(fill)
        intents.append(
            OrderIntent(side=side, order_type=IntentType.MARKET, quantity=quantity, decided_at=utc(2026, 1, 1, 8, 0))
        )
        outcomes.append(FillOutcome(intent_index=index, filled=True, fill=fill))
    if curve is None:
        curve = (EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100000")),)
    return BacktestRun(
        mode=BacktestTradingMode.BACKTEST,
        input_sha256="a" * 64,
        dataset_id="ds",
        source="unit",
        initial_capital=Decimal("100000"),
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        intents=tuple(intents),
        outcomes=tuple(outcomes),
        trades=trades,
        equity_curve=curve,
    )


def fixture_a() -> object:
    """Engine-built 3-trade run with realized P&L (+10, -4, +2)."""
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
    return run_backtest(
        inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
        intents=intents,
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        initial_capital=Decimal("100000"),
    )


class TestTradeStatisticsHappyPath:
    def test_net_profit(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.net_profit == Decimal("8")

    def test_loss_rate(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.loss_rate == Decimal("1") / Decimal("3")

    def test_expectancy_is_mean_pnl(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.expectancy == Decimal("8") / Decimal("3")

    def test_average_win(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.avg_win == Decimal("6")

    def test_average_loss_is_positive_magnitude(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.avg_loss == Decimal("4")

    def test_risk_reward_ratio(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.risk_reward_ratio == Decimal("1.5")

    def test_largest_win_and_loss(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.largest_win == Decimal("10")
        assert report.statistics.largest_loss == Decimal("4")

    def test_consecutive_streaks_single(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.max_consecutive_wins == 1
        assert report.statistics.max_consecutive_losses == 1

    def test_average_trade_duration(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.average_trade_duration == timedelta(minutes=1)

    def test_recovery_factor(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.recovery_factor == Decimal("2")

    def test_total_fees_and_slippage_zero(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.total_fees == Decimal("0")
        assert report.statistics.total_slippage == Decimal("0")


class TestTradeStatisticsStreaks:
    def _report(self, pnls: tuple[str, ...]) -> BacktestReport:
        trades = tuple(make_trade(index, pnl) for index, pnl in enumerate(pnls))
        run = make_run(trades)
        return build_report(run, risk_free_rate_per_period=Decimal("0"))

    def test_wwlllw_streaks(self) -> None:
        report = self._report(("10", "5", "-4", "-2", "-1", "6"))
        assert report.statistics.max_consecutive_wins == 2
        assert report.statistics.max_consecutive_losses == 3

    def test_all_wins_streak(self) -> None:
        report = self._report(("5", "1", "3"))
        assert report.statistics.max_consecutive_wins == 3
        assert report.statistics.max_consecutive_losses == 0

    def test_all_losses_streak(self) -> None:
        report = self._report(("-1", "-2", "-3"))
        assert report.statistics.max_consecutive_wins == 0
        assert report.statistics.max_consecutive_losses == 3

    def test_breakeven_breaks_streak(self) -> None:
        report = self._report(("5", "0", "3"))
        assert report.statistics.max_consecutive_wins == 1

    def test_zero_gross_loss_policies(self) -> None:
        report = self._report(("2", "1"))
        assert report.metrics.gross_loss == Decimal("0")
        assert report.metrics.profit_factor is None
        assert report.statistics.avg_loss is None
        assert report.statistics.risk_reward_ratio is None
        assert report.statistics.largest_loss is None
        assert report.statistics.loss_rate == Decimal("0")


class TestTradeStatisticsEmpty:
    def test_empty_trades_none_and_zero(self) -> None:
        run = make_run(())
        report = build_report(run, risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.net_profit == Decimal("0")
        assert report.metrics.trade_count == 0
        assert report.statistics.loss_rate is None
        assert report.statistics.expectancy is None
        assert report.statistics.avg_win is None
        assert report.statistics.avg_loss is None
        assert report.statistics.risk_reward_ratio is None
        assert report.statistics.largest_win is None
        assert report.statistics.largest_loss is None
        assert report.statistics.max_consecutive_wins == 0
        assert report.statistics.max_consecutive_losses == 0
        assert report.statistics.average_trade_duration is None
        assert report.statistics.recovery_factor is None

    def test_empty_trades_declining_curve_recovery_none(self) -> None:
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("110")),
            EquityPoint(utc(2026, 1, 1, 9, 2), Decimal("105")),
        )
        run = make_run((), curve=curve)
        report = build_report(run, risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.recovery_factor is None


class TestTradeStatisticsDuration:
    def test_recovery_factor_uses_dollar_drawdown(self) -> None:
        # net_profit=5, max_drawdown_dollar=10 -> recovery 0.5; distinct from
        # gross_loss (5) which would wrongly yield 1, and from the ratio
        # denominator (10/110) which would wrongly yield 55.
        trades = (make_trade(0, "10"), make_trade(1, "-5"))
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("110")),
            EquityPoint(utc(2026, 1, 1, 9, 2), Decimal("100")),
            EquityPoint(utc(2026, 1, 1, 9, 3), Decimal("110")),
        )
        run = make_run(trades, curve=curve)
        report = build_report(run, risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.net_profit == Decimal("5")
        assert report.statistics.recovery_factor == Decimal("0.5")

    def test_multi_exit_uses_max_exit_timestamp(self) -> None:
        trade = make_trade(0, "140", entry_seq=0, exit_seqs=(1, 2))
        run = make_run(
            (trade,),
            fill_times={
                0: utc(2026, 1, 1, 9, 1),
                1: utc(2026, 1, 1, 9, 2),
                2: utc(2026, 1, 1, 9, 3),
            },
        )
        report = build_report(run, risk_free_rate_per_period=Decimal("0"))
        assert report.statistics.average_trade_duration == timedelta(minutes=2)

    def test_frozen_and_decimal_types(self) -> None:
        report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
        stats = report.statistics
        assert isinstance(stats.net_profit, Decimal)
        assert isinstance(stats.max_consecutive_wins, int)
        assert isinstance(stats.average_trade_duration, timedelta)
        with pytest.raises(Exception):
            stats.net_profit = Decimal("1")  # type: ignore[misc]
