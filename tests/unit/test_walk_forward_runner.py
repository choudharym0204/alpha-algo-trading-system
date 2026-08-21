from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from dataclasses import FrozenInstanceError

from alpha_algo_contracts import MarketTick
from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    compute_metrics,
    run_backtest,
)
from alpha_algo_walk_forward import (
    RUNNER_FAILURE_POLICY,
    WalkForwardConfig,
    WalkForwardError,
    WindowBacktestResult,
    build_windows,
    run_walk_forward,
)

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
UTC = timezone.utc


def utc(y, mo, d, h=9, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def tick(ts: datetime, ltp: str, bid: str, ask: str) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def demo_input() -> BacktestInput:
    records = tuple(
        tick(
            utc(2026, 1, 2, 9, 0) + timedelta(minutes=i),
            str(100 + 2 * i),
            str(100 + 2 * i - 0.5),
            str(100 + 2 * i + 0.5),
        )
        for i in range(40)
    )
    return BacktestInput(dataset_id="ds", source="unit", records=records)


DEMO_CONFIG = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)


def slice_metrics(slice_input: BacktestInput):
    first = slice_input.first_timestamp
    buy = OrderIntent(
        side=IntentSide.BUY,
        order_type=IntentType.MARKET,
        quantity=Decimal("10"),
        decided_at=first - timedelta(seconds=30),
    )
    sell = OrderIntent(
        side=IntentSide.SELL,
        order_type=IntentType.MARKET,
        quantity=Decimal("10"),
        decided_at=first + timedelta(seconds=20),
    )
    run = run_backtest(
        inputs=slice_input,
        intents=(buy, sell),
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        initial_capital=Decimal("100000"),
    )
    return compute_metrics(run, risk_free_rate_per_period=Decimal("0"))


def demo_runner(window):
    return WindowBacktestResult(
        window=window,
        is_metrics=slice_metrics(window.in_sample_input),
        oos_metrics=slice_metrics(window.test_input),
    )


class TestRunnerContract:
    def test_runner_called_once_per_window_in_order(self) -> None:
        calls: list[int] = []
        inputs = demo_input()

        def spy(window) -> WindowBacktestResult:
            calls.append(window.index)
            return demo_runner(window)

        result = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=spy)
        assert calls == [0, 1, 2]
        assert len(result.periods) == 3 == len(build_windows(inputs=inputs, config=DEMO_CONFIG))

    def test_runner_receives_built_windows(self) -> None:
        inputs = demo_input()
        expected = build_windows(inputs=inputs, config=DEMO_CONFIG)
        captured: list = []
        _ = run_walk_forward(
            inputs=inputs,
            config=DEMO_CONFIG,
            window_runner=lambda window: (
                captured.append(window),
                demo_runner(window),
            )[1],
        )
        assert captured == list(expected)

    def test_runner_single_positional_argument(self) -> None:
        inputs = demo_input()

        def one_arg(window) -> WindowBacktestResult:
            assert isinstance(window.index, int)
            return demo_runner(window)

        result = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=one_arg)
        assert len(result.periods) == 3

    def test_wrong_result_type_rejected_typed(self) -> None:
        inputs = demo_input()
        for bad in (42, None, "x"):
            with pytest.raises(WalkForwardError, match="WindowBacktestResult"):
                run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=lambda window: bad)  # type: ignore[return-value]

    def test_backtest_run_as_result_rejected(self) -> None:
        # The plausible honest mistake: returning a raw engine run instead of
        # a WindowBacktestResult.
        inputs = demo_input()
        first = inputs.first_timestamp
        intent = OrderIntent(
            side=IntentSide.BUY,
            order_type=IntentType.MARKET,
            quantity=Decimal("1"),
            decided_at=first - timedelta(seconds=30),
        )
        raw_run = run_backtest(
            inputs=inputs,
            intents=(intent,),
            cost_model=CostModel(Decimal("0"), Decimal("0")),
            initial_capital=Decimal("100000"),
        )
        with pytest.raises(WalkForwardError, match="WindowBacktestResult"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=lambda window: raw_run)  # type: ignore[return-value]

    def test_foreign_window_result_rejected(self) -> None:
        inputs = demo_input()
        windows = build_windows(inputs=inputs, config=DEMO_CONFIG)
        foreign = demo_runner(windows[2])

        def wrong_window(window) -> WindowBacktestResult:
            return WindowBacktestResult(
                window=windows[2],
                is_metrics=foreign.is_metrics,
                oos_metrics=foreign.oos_metrics,
            )

        with pytest.raises(WalkForwardError, match="different window"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=wrong_window)

    def test_invalid_metrics_in_result_rejected(self) -> None:
        inputs = demo_input()
        good = demo_runner(build_windows(inputs=inputs, config=DEMO_CONFIG)[0])

        def float_metric(window) -> WindowBacktestResult:
            from alpha_algo_backtest_engine import BacktestMetrics

            return WindowBacktestResult(
                window=window,
                is_metrics=BacktestMetrics(
                    initial_capital=Decimal("100000"),
                    final_equity=Decimal("100000"),
                    total_return=0.5,  # float, not Decimal
                    trade_count=1,
                    wins=1,
                    losses=0,
                    breakevens=0,
                    win_rate=Decimal("1"),
                    gross_profit=Decimal("10"),
                    gross_loss=Decimal("0"),
                    profit_factor=None,
                    max_drawdown=Decimal("0"),
                    sharpe_ratio=None,
                    risk_free_rate_per_period=Decimal("0"),
                ),
                oos_metrics=good.oos_metrics,
            )

        with pytest.raises(WalkForwardError, match="is_metrics.total_return"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=float_metric)

    def test_non_finite_metric_rejected(self) -> None:
        inputs = demo_input()
        good = demo_runner(build_windows(inputs=inputs, config=DEMO_CONFIG)[0])

        def nan_metric(window) -> WindowBacktestResult:
            from alpha_algo_backtest_engine import BacktestMetrics

            return WindowBacktestResult(
                window=window,
                is_metrics=good.is_metrics,
                oos_metrics=BacktestMetrics(
                    initial_capital=Decimal("100000"),
                    final_equity=Decimal("100000"),
                    total_return=Decimal("NaN"),
                    trade_count=1,
                    wins=1,
                    losses=0,
                    breakevens=0,
                    win_rate=Decimal("1"),
                    gross_profit=Decimal("10"),
                    gross_loss=Decimal("0"),
                    profit_factor=None,
                    max_drawdown=Decimal("0"),
                    sharpe_ratio=None,
                    risk_free_rate_per_period=Decimal("0"),
                ),
            )

        with pytest.raises(WalkForwardError, match="oos_metrics.total_return"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=nan_metric)

    def test_win_rate_out_of_range_rejected(self) -> None:
        inputs = demo_input()
        good = demo_runner(build_windows(inputs=inputs, config=DEMO_CONFIG)[0])

        def bad_win_rate(window) -> WindowBacktestResult:
            from alpha_algo_backtest_engine import BacktestMetrics

            return WindowBacktestResult(
                window=window,
                is_metrics=good.is_metrics,
                oos_metrics=BacktestMetrics(
                    initial_capital=Decimal("100000"),
                    final_equity=Decimal("100000"),
                    total_return=Decimal("0.0001"),
                    trade_count=1,
                    wins=1,
                    losses=0,
                    breakevens=0,
                    win_rate=Decimal("1.5"),
                    gross_profit=Decimal("10"),
                    gross_loss=Decimal("0"),
                    profit_factor=None,
                    max_drawdown=Decimal("0"),
                    sharpe_ratio=None,
                    risk_free_rate_per_period=Decimal("0"),
                ),
            )

        with pytest.raises(WalkForwardError, match="oos_metrics.win_rate"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=bad_win_rate)

    def test_periods_stored_independently(self) -> None:
        inputs = demo_input()
        windows = build_windows(inputs=inputs, config=DEMO_CONFIG)
        results = [demo_runner(window) for window in windows]
        periods = tuple(results)
        assert periods[0] is results[0]
        assert periods[1] is results[1]
        assert periods[2] is results[2]
        with pytest.raises(FrozenInstanceError):
            results[0].metadata = {"x": 1}  # type: ignore[misc]

    def test_period_exception_propagates_unchanged(self) -> None:
        inputs = demo_input()
        boom = RuntimeError("boom")

        def failing(window) -> WindowBacktestResult:
            if window.index == 1:
                raise boom
            return demo_runner(window)

        with pytest.raises(RuntimeError) as exc_info:
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=failing)
        assert exc_info.value is boom

    def test_no_partial_result_on_failure(self) -> None:
        inputs = demo_input()

        def failing(window) -> WindowBacktestResult:
            if window.index == 2:
                raise ValueError("late failure")
            return demo_runner(window)

        with pytest.raises(ValueError, match="late failure"):
            run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=failing)

    def test_result_echoes_manifest_and_config(self) -> None:
        inputs = demo_input()
        result = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=demo_runner)
        assert result.input_sha256 == inputs.content_sha256
        assert result.dataset_id == "ds"
        assert result.source == "unit"
        assert result.config == DEMO_CONFIG
        assert result.record_count == 40

    def test_coverage_metadata_exact(self) -> None:
        inputs = demo_input()
        result = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=demo_runner)
        # Windows at starts 0, 10, 20, each spanning [start, start+20):
        # [0,20) U [10,30) U [20,40) = [0,40) -> full coverage.
        assert result.covered_records == 40
        assert result.uncovered_records == 0

    def test_coverage_metadata_remainder(self) -> None:
        inputs = demo_input()
        config = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=15)
        result = run_walk_forward(inputs=inputs, config=config, window_runner=demo_runner)
        # Windows at starts 0 and 15: [0,20) U [15,35) = [0,35); records [35,40) unused.
        assert len(result.periods) == 2
        assert result.covered_records == 35
        assert result.uncovered_records == 5

    def test_coverage_metadata_full_tile(self) -> None:
        records = tuple(
            tick(utc(2026, 1, 2, 9, 0) + timedelta(minutes=i), "100", "99.5", "100.5")
            for i in range(100)
        )
        inputs = BacktestInput(dataset_id="ds", source="unit", records=records)
        config = WalkForwardConfig(training_records=20, validation_records=20, test_records=20, step_records=20)
        result = run_walk_forward(inputs=inputs, config=config, window_runner=demo_runner)
        assert result.covered_records == 100
        assert result.uncovered_records == 0

    def test_no_cross_run_state(self) -> None:
        inputs = demo_input()
        first = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=demo_runner)
        # Interleave a different run.
        other_config = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)
        run_walk_forward(inputs=inputs, config=other_config, window_runner=demo_runner)
        second = run_walk_forward(inputs=inputs, config=DEMO_CONFIG, window_runner=demo_runner)
        assert second == first


class TestDemoRunnerComposition:
    def test_demo_composition_exact_metrics(self) -> None:
        result = run_walk_forward(inputs=demo_input(), config=DEMO_CONFIG, window_runner=demo_runner)
        for period in result.periods:
            for metrics in (period.is_metrics, period.oos_metrics):
                assert metrics.trade_count == 1
                assert metrics.wins == 1
                assert metrics.losses == 0
                assert metrics.breakevens == 0
                assert metrics.win_rate == Decimal("1")
                assert metrics.gross_profit == Decimal("10")
                assert metrics.gross_loss == Decimal("0")
                assert metrics.profit_factor is None
                assert metrics.total_return == Decimal("0.0001")
                assert metrics.final_equity == Decimal("100010")
                assert metrics.initial_capital == Decimal("100000")
                assert metrics.max_drawdown == Decimal("0")
            # IS covers 15 records (train 10 + validation 5): returns [r, 0 x14]
            # -> sharpe = 1/sqrt(13). OOS covers 5 records: returns [r, 0 x4]
            # -> sharpe = 1/sqrt(3). Each op rounds at precision 28, so compare
            # within 1e-25 of the closed form (engine-verified).
            is_expected = (Decimal("1") / Decimal("13")).sqrt()
            oos_expected = (Decimal("1") / Decimal("3")).sqrt()
            assert abs(period.is_metrics.sharpe_ratio - is_expected) < Decimal("1e-25")
            assert abs(period.oos_metrics.sharpe_ratio - oos_expected) < Decimal("1e-25")

    def test_demo_all_periods_equal(self) -> None:
        result = run_walk_forward(inputs=demo_input(), config=DEMO_CONFIG, window_runner=demo_runner)
        assert result.periods[0].is_metrics == result.periods[1].is_metrics == result.periods[2].is_metrics
        assert result.periods[0].oos_metrics == result.periods[1].oos_metrics == result.periods[2].oos_metrics

    def test_demo_aggregate_well_defined(self) -> None:
        result = run_walk_forward(inputs=demo_input(), config=DEMO_CONFIG, window_runner=demo_runner)
        assert result.aggregate.period_count == 3
        for entry in result.aggregate.metrics:
            if entry.metric == "profit_factor":
                # All periods have gross_loss == 0 -> profit_factor is None everywhere.
                assert entry.is_stats.count == 0
                assert entry.oos_stats.count == 0
            else:
                assert entry.is_stats.count == 3
                assert entry.oos_stats.count == 3

    def test_failure_policy_constant_fixed(self) -> None:
        assert isinstance(RUNNER_FAILURE_POLICY, str)
        assert "aborts" in RUNNER_FAILURE_POLICY
