from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    BacktestEngineError,
    BacktestMetricsError,
    BacktestRun,
    CostModel,
    EquityPoint,
    IntentSide,
    IntentType,
    OrderIntent,
    UnfilledReason,
    compute_metrics,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput, BacktestTradingMode

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


def run(*intents: OrderIntent, commission: str = "0", slippage: str = "0") -> BacktestRun:
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


def metrics(run_obj: BacktestRun, rf: str = "0") -> object:
    return compute_metrics(run_obj, risk_free_rate_per_period=Decimal(rf))


class TestReturnAndTrades:
    def test_no_intents_flat_equity_and_undefined_ratios(self) -> None:
        result = run()
        m = metrics(result)
        assert m.trade_count == 0
        assert m.total_return == Decimal("0")
        assert m.win_rate is None
        assert m.profit_factor is None
        assert m.max_drawdown == Decimal("0")
        assert m.sharpe_ratio is None
        assert m.final_equity == Decimal("100000")

    def test_all_unfilled_metrics_match_flat_run(self) -> None:
        result = run(order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 20), limit_price="50"))
        m = metrics(result)
        assert m.trade_count == 0
        assert m.total_return == Decimal("0")
        assert m.win_rate is None
        assert m.profit_factor is None

    def test_all_rejected_metrics_match_flat_run(self) -> None:
        result = run(order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)))
        (outcome,) = result.outcomes
        assert outcome.reason == UnfilledReason.INSUFFICIENT_POSITION.value
        m = metrics(result)
        assert m.trade_count == 0
        assert m.total_return == Decimal("0")

    def test_total_return_formula(self) -> None:
        # Round trip: buy 10 @102.5, sell 10 @103.5 => pnl 0 with 5+5 commission.
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
            commission="5",
        )
        m = metrics(result)
        assert m.trade_count == 1
        assert m.total_return == Decimal("0")

    def test_profitable_round_trip_counts_win(self) -> None:
        # Buy 10 @102.5, sell 10 @105.5 (rec3 bid): pnl = 30 - 10 = 20.
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30)),
            commission="5",
        )
        m = metrics(result)
        assert m.trade_count == 1
        assert m.wins == 1
        assert m.losses == 0
        assert m.breakevens == 0
        assert m.win_rate == Decimal("1")
        assert m.gross_profit == Decimal("20")
        assert m.gross_loss == Decimal("0")
        assert m.profit_factor is None  # gross_loss == 0 => None, never Infinity


class TestProfitFactor:
    def test_profit_factor_is_gross_profit_over_gross_loss(self) -> None:
        # Trade 1: buy 10 @102.5 (rec1 ask), sell 10 @109.5 (rec2 bid) => +60 net (comm 5+5).
        # Trade 2: buy 10 @104.5 (rec3 ask), sell 10 @100 (rec3 bid) => -55 net (comm 5+5).
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "102", "101.5", "102.5"),
            tick(utc(2026, 1, 1, 9, 2), "110", "109.5", "110.5"),
            tick(utc(2026, 1, 1, 9, 3), "102", "100", "104.5"),
        )
        result = run_backtest(
            inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
            intents=(
                order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
                order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
                order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 20)),
                order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30)),
            ),
            cost_model=CostModel(commission_per_fill=Decimal("5"), slippage_bps=Decimal("0")),
            initial_capital=Decimal("100000"),
        )
        m = metrics(result)
        assert m.trade_count == 2
        assert m.gross_profit == Decimal("60")
        assert m.gross_loss == Decimal("55")
        assert m.profit_factor == Decimal("60") / Decimal("55")


class TestMaxDrawdown:
    def test_max_drawdown_over_equity_curve(self) -> None:
        # Equity: 100000 -> 100020 -> 99950 -> 100000.
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100000")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("100020")),
            EquityPoint(utc(2026, 1, 1, 9, 2), Decimal("99950")),
            EquityPoint(utc(2026, 1, 1, 9, 3), Decimal("100000")),
        )
        run_obj = _run_with_curve(curve)
        m = metrics(run_obj)
        assert m.max_drawdown == Decimal("70") / Decimal("100020")

    def test_monotonic_curve_has_zero_drawdown(self) -> None:
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100000")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("100100")),
            EquityPoint(utc(2026, 1, 1, 9, 2), Decimal("100200")),
        )
        m = metrics(_run_with_curve(curve))
        assert m.max_drawdown == Decimal("0")


class TestSharpe:
    def test_constant_equity_sharpe_is_none(self) -> None:
        m = metrics(run())
        assert m.sharpe_ratio is None

    def test_single_record_sharpe_is_none(self) -> None:
        records = (tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),)
        result = run_backtest(
            inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
            intents=(),
            cost_model=CostModel(Decimal("0"), Decimal("0")),
            initial_capital=Decimal("100000"),
        )
        m = metrics(result)
        assert m.sharpe_ratio is None

    def test_sharpe_uses_injected_risk_free_rate(self) -> None:
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100000")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("101000")),
            EquityPoint(utc(2026, 1, 1, 9, 2), Decimal("100500")),
            EquityPoint(utc(2026, 1, 1, 9, 3), Decimal("102000")),
        )
        run_obj = _run_with_curve(curve)
        m0 = metrics(run_obj, rf="0")
        m1 = metrics(run_obj, rf="0.01")
        assert m0.sharpe_ratio is not None
        assert m1.sharpe_ratio is not None
        assert m1.sharpe_ratio < m0.sharpe_ratio  # higher rf => lower sharpe

    def test_risk_free_rate_validation(self) -> None:
        result = run()
        with pytest.raises(BacktestEngineError):
            compute_metrics(result, risk_free_rate_per_period=Decimal("-0.01"))
        with pytest.raises(BacktestEngineError):
            compute_metrics(result, risk_free_rate_per_period=Decimal("Infinity"))
        with pytest.raises(BacktestEngineError):
            compute_metrics(result, risk_free_rate_per_period=0.01)  # type: ignore[arg-type]


class TestFailLoud:
    def test_non_positive_equity_raises_metrics_error(self) -> None:
        curve = (
            EquityPoint(utc(2026, 1, 1, 9, 0), Decimal("100000")),
            EquityPoint(utc(2026, 1, 1, 9, 1), Decimal("0")),
        )
        run_obj = _run_with_curve(curve)
        with pytest.raises(BacktestMetricsError):
            metrics(run_obj)

    def test_metrics_echo_inputs(self) -> None:
        result = run(
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
        )
        m = metrics(result, rf="0.005")
        assert m.initial_capital == Decimal("100000")
        assert m.risk_free_rate_per_period == Decimal("0.005")
        assert m.final_equity == result.final_equity


def _run_with_curve(curve: tuple[EquityPoint, ...]) -> BacktestRun:
    """Build a BacktestRun directly with a hand-crafted equity curve."""
    return BacktestRun(
        mode=BacktestTradingMode.BACKTEST,
        input_sha256="a" * 64,
        dataset_id="ds",
        source="unit",
        initial_capital=Decimal("100000"),
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        intents=(),
        outcomes=(),
        trades=(),
        equity_curve=curve,
    )
