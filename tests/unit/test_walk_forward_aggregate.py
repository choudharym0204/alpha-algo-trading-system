from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from dataclasses import FrozenInstanceError

from alpha_algo_contracts import MarketTick
from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import BacktestMetrics
from alpha_algo_walk_forward import (
    AGGREGATED_METRICS,
    DEGRADATION_DIRECTIONS,
    DEGRADATION_METRICS,
    METRIC_AGGREGATION_POLICY,
    WalkForwardAggregate,
    WalkForwardConfig,
    WalkForwardError,
    WindowBacktestResult,
    aggregate_periods,
    build_windows,
)

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
UTC = timezone.utc


def utc(y, mo, d, h=9, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def tick(ts: datetime) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal("100"),
        bid=Decimal("99.5"),
        ask=Decimal("100.5"),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def _input(record_count: int) -> BacktestInput:
    records = tuple(tick(utc(2026, 1, 2, 9, 0) + timedelta(minutes=i)) for i in range(record_count))
    return BacktestInput(dataset_id="ds", source="unit", records=records)


def _metrics(total_return, trade_count=5, win_rate=Decimal("0.6"), profit_factor=Decimal("1.5"), max_drawdown=Decimal("0.1"), sharpe_ratio=Decimal("0.5")):
    return BacktestMetrics(
        initial_capital=Decimal("100000"),
        final_equity=Decimal("100000"),
        total_return=total_return if isinstance(total_return, Decimal) else Decimal(str(total_return)),
        trade_count=trade_count,
        wins=3,
        losses=2,
        breakevens=0,
        win_rate=win_rate,
        gross_profit=Decimal("150"),
        gross_loss=Decimal("100"),
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        risk_free_rate_per_period=Decimal("0"),
    )


def _windows(count: int):
    inputs = _input(60)
    config = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)
    return build_windows(inputs=inputs, config=config)[:count]


def _periods(count: int, *, oos_returns, is_returns=None, oos_trades=None, sharpe_values=None, oos_max_drawdown=None):
    windows = _windows(count)
    periods = []
    for k in range(count):
        is_metrics = _metrics(
            is_returns[k] if is_returns is not None else Decimal("0.10"),
            trade_count=8,
            sharpe_ratio=Decimal("0.4"),
        )
        kwargs = {}
        if oos_trades is not None:
            kwargs["trade_count"] = oos_trades[k]
        if sharpe_values is not None:
            kwargs["sharpe_ratio"] = sharpe_values[k]
        if oos_max_drawdown is not None:
            kwargs["max_drawdown"] = oos_max_drawdown[k]
        oos_metrics = _metrics(oos_returns[k], **kwargs)
        periods.append(WindowBacktestResult(window=windows[k], is_metrics=is_metrics, oos_metrics=oos_metrics))
    return tuple(periods)


class TestMetricStats:
    def test_mean_median_stdev_equal_values(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.mean == Decimal("0.10")
        assert stats.median == Decimal("0.10")
        assert stats.stdev == Decimal("0")
        assert stats.count == 3

    def test_mean_median_stdev_two_point(self) -> None:
        aggregate = aggregate_periods(periods=_periods(2, oos_returns=[0.00, 0.30]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.mean == Decimal("0.15")
        assert stats.median == Decimal("0.15")
        # Population stdev: sqrt(0.0225) = 0.15 (sample would be 0.2121...).
        assert stats.stdev == Decimal("0.15")

    def test_four_point_perfect_square(self) -> None:
        aggregate = aggregate_periods(periods=_periods(4, oos_returns=[0.00, 0.00, 0.30, 0.30]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.mean == Decimal("0.15")
        assert stats.median == Decimal("0.15")
        assert stats.stdev == Decimal("0.15")

    def test_median_odd_count(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.20, 0.30]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.median == Decimal("0.20")
        assert stats.mean == Decimal("0.20")

    def test_median_even_count(self) -> None:
        aggregate = aggregate_periods(periods=_periods(2, oos_returns=[0.10, 0.20]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.median == Decimal("0.15")

    def test_stdev_is_population_not_sample(self) -> None:
        aggregate = aggregate_periods(periods=_periods(2, oos_returns=[0.00, 0.30]))
        assert aggregate.metrics[0].oos_stats.stdev == Decimal("0.15")  # ÷n, not ÷(n-1)

    def test_all_stats_are_decimal(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.20, 0.30]))
        for entry in aggregate.metrics:
            for stats in (entry.is_stats, entry.oos_stats):
                for value in (stats.mean, stats.median, stats.stdev):
                    assert value is None or type(value) is Decimal

    def test_empty_periods_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="non-empty"):
            aggregate_periods(periods=())

    def test_single_period_aggregate(self) -> None:
        aggregate = aggregate_periods(periods=_periods(1, oos_returns=[0.10]))
        stats = aggregate.metrics[0].oos_stats
        assert stats.mean == Decimal("0.10")
        assert stats.median == Decimal("0.10")
        assert stats.stdev is None  # single-value dispersion is not assessable
        assert stats.count == 1

    def test_none_metric_all_none(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10], sharpe_values=[None, None, None]))
        sharpe = next(entry for entry in aggregate.metrics if entry.metric == "sharpe_ratio")
        assert sharpe.oos_stats.mean is None
        assert sharpe.oos_stats.median is None
        assert sharpe.oos_stats.stdev is None
        assert sharpe.oos_stats.count == 0

    def test_none_metric_mixed(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10], sharpe_values=[None, Decimal("0.10"), Decimal("0.30")]))
        sharpe = next(entry for entry in aggregate.metrics if entry.metric == "sharpe_ratio")
        assert sharpe.oos_stats.mean == Decimal("0.20")
        assert sharpe.oos_stats.count == 2

    def test_aggregate_is_frozen(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        with pytest.raises(FrozenInstanceError):
            aggregate.period_count = 99  # type: ignore[misc]

    def test_aggregate_rejects_non_tuple(self) -> None:
        with pytest.raises(WalkForwardError, match="non-empty tuple"):
            aggregate_periods(periods=list(_periods(2, oos_returns=[0.10, 0.10])))  # type: ignore[arg-type]

    def test_aggregate_rejects_non_result(self) -> None:
        with pytest.raises(WalkForwardError, match="WindowBacktestResult"):
            aggregate_periods(periods=("x",))  # type: ignore[list-item]

    def test_aggregate_rejects_shuffled_periods(self) -> None:
        periods = _periods(3, oos_returns=[0.10, 0.10, 0.10])
        with pytest.raises(WalkForwardError, match="strictly ascending"):
            aggregate_periods(periods=tuple(reversed(periods)))

    def test_period_count_matches(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        assert aggregate.period_count == 3

    def test_aggregated_metric_set_exact(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        assert [entry.metric for entry in aggregate.metrics] == list(AGGREGATED_METRICS)


class TestDegradation:
    def test_degradation_ratio_formula(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.05, 0.05, 0.05]))
        total_return = next(entry for entry in aggregate.metrics if entry.metric == "total_return")
        assert total_return.degradation == Decimal("0.50")  # (0.10 - 0.05) / 0.10

    def test_degradation_sign_oos_better(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.15, 0.15, 0.15]))
        total_return = next(entry for entry in aggregate.metrics if entry.metric == "total_return")
        assert total_return.degradation == Decimal("-0.50")  # negative = OOS better; not clamped

    def test_degradation_division_by_zero_is_none(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.00, 0.00, 0.00], is_returns=[0.00, 0.00, 0.00]))
        total_return = next(entry for entry in aggregate.metrics if entry.metric == "total_return")
        assert total_return.degradation is None  # never Infinity, never a crash

    def test_degradation_negative_is_is_negative(self) -> None:
        aggregate = aggregate_periods(
            periods=_periods(3, oos_returns=[-0.05, -0.05, -0.05], is_returns=[-0.10, -0.10, -0.10])
        )
        total_return = next(entry for entry in aggregate.metrics if entry.metric == "total_return")
        assert total_return.degradation == Decimal("-0.50")  # (-0.10 - (-0.05)) / |-0.10|

    def test_degradation_oos_double_is_minus_one(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10], is_returns=[0.05, 0.05, 0.05]))
        total_return = next(entry for entry in aggregate.metrics if entry.metric == "total_return")
        assert total_return.degradation == Decimal("-1.00")

    def test_degradation_max_drawdown_direction(self) -> None:
        # max_drawdown: lower is better, so a LARGER OOS drawdown degrades.
        aggregate = aggregate_periods(
            periods=_periods(3, oos_returns=[0.10, 0.10, 0.10], oos_max_drawdown=[Decimal("0.15"), Decimal("0.15"), Decimal("0.15")])
        )
        max_dd = next(entry for entry in aggregate.metrics if entry.metric == "max_drawdown")
        assert DEGRADATION_DIRECTIONS["max_drawdown"] == -1
        # -1 * (0.10 - 0.15) / 0.10 = +0.50 (OOS worse)
        assert max_dd.degradation == Decimal("0.50")

    def test_degradation_trade_count_always_none(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        trade_count = next(entry for entry in aggregate.metrics if entry.metric == "trade_count")
        assert trade_count.degradation is None

    def test_degradation_metric_set_exact(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        degraded = [entry.metric for entry in aggregate.metrics if entry.degradation is not None]
        assert set(degraded) <= set(DEGRADATION_METRICS)

    def test_degradation_trade_count_stats_still_computed(self) -> None:
        aggregate = aggregate_periods(periods=_periods(3, oos_returns=[0.10, 0.10, 0.10]))
        trade_count = next(entry for entry in aggregate.metrics if entry.metric == "trade_count")
        assert trade_count.oos_stats.mean == Decimal("5")
        assert trade_count.oos_stats.count == 3

    def test_policy_constant_fixed(self) -> None:
        assert isinstance(METRIC_AGGREGATION_POLICY, str)
        assert "POPULATION" in METRIC_AGGREGATION_POLICY
        assert "trade_count" in METRIC_AGGREGATION_POLICY

    def test_hand_constructed_aggregate_validated(self) -> None:
        from alpha_algo_walk_forward import MetricAggregate, MetricStats

        with pytest.raises(WalkForwardError, match="AGGREGATED_METRICS"):
            MetricAggregate(metric="nope", is_stats=MetricStats(None, None, None, 0), oos_stats=MetricStats(None, None, None, 0), degradation=None)

    def test_walk_forward_aggregate_rejects_wrong_order(self) -> None:
        from alpha_algo_walk_forward import MetricAggregate, MetricStats

        stats = MetricStats(mean=None, median=None, stdev=None, count=0)
        entries = tuple(
            MetricAggregate(metric=metric, is_stats=stats, oos_stats=stats, degradation=None)
            for metric in reversed(list(AGGREGATED_METRICS))
        )
        with pytest.raises(WalkForwardError, match="AGGREGATED_METRICS order"):
            WalkForwardAggregate(period_count=3, metrics=entries)
