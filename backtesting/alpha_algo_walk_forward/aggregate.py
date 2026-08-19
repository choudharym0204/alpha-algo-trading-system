"""Cross-window aggregation for the walk-forward testing harness (P7-003).

``aggregate_periods`` computes per-metric cross-window statistics (mean,
median, population standard deviation) and IS-vs-OOS degradation over the
five scale-free core metrics. All arithmetic is exact Decimal under a fixed
``localcontext`` (precision 28, imported from the P7-002 engine); there is
no ``math``, no ``statistics``, and no float path. Undefined ratios are
``None`` — never 0, never Infinity, never a crash. ``trade_count`` gets
statistics but never a degradation value: IS and OOS windows cover unequal
record counts, so raw trade counts are structurally incomparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Mapping

from alpha_algo_backtest_engine import DECIMAL_PRECISION

from alpha_algo_walk_forward.errors import WalkForwardError

if TYPE_CHECKING:
    from alpha_algo_walk_forward.results import WindowBacktestResult

__all__ = [
    "AGGREGATED_METRICS",
    "DEGRADATION_DIRECTIONS",
    "DEGRADATION_METRICS",
    "METRIC_AGGREGATION_POLICY",
    "MetricAggregate",
    "MetricStats",
    "WalkForwardAggregate",
    "aggregate_periods",
]

METRIC_AGGREGATION_POLICY = (
    "Cross-window stats are computed per metric over the windows where that metric is "
    "defined (None values excluded; each MetricStats.count records how many windows "
    "contributed). Mean = sum/n; median = middle value (odd n) or mean of the two middle "
    "values (even n); stdev = POPULATION standard deviation, None when fewer than 2 "
    "windows contribute. Degradation uses cross-window means of the five scale-free "
    "metrics only (trade_count is excluded: IS and OOS windows cover unequal record "
    "counts, so raw counts are structurally incomparable); all arithmetic is Decimal "
    "under DECIMAL_PRECISION. Undefined values are None - never 0, never Infinity, "
    "never a crash."
)

AGGREGATED_METRICS: tuple[str, ...] = (
    "total_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "sharpe_ratio",
    "trade_count",
)

DEGRADATION_METRICS: tuple[str, ...] = (
    "total_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "sharpe_ratio",
)

# +1 = higher is better; -1 = lower is better (max_drawdown). Lookup-only,
# never iterated (determinism commitment: no dict-order dependence).
DEGRADATION_DIRECTIONS: Mapping[str, int] = {
    "total_return": 1,
    "win_rate": 1,
    "profit_factor": 1,
    "max_drawdown": -1,
    "sharpe_ratio": 1,
}


@dataclass(frozen=True)
class MetricStats:
    """Cross-window statistics for one metric over one role (IS or OOS)."""

    mean: Decimal | None
    median: Decimal | None
    stdev: Decimal | None
    count: int

    def __post_init__(self) -> None:
        for name, value in (("mean", self.mean), ("median", self.median), ("stdev", self.stdev)):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise WalkForwardError(f"{name} must be None or a finite Decimal")
        if type(self.count) is not int or self.count < 0:
            raise WalkForwardError("count must be a non-negative int")
        if self.count == 0:
            if self.mean is not None or self.median is not None or self.stdev is not None:
                raise WalkForwardError("count == 0 requires all stats to be None")
        else:
            if self.mean is None or self.median is None:
                raise WalkForwardError("count > 0 requires mean and median to be defined")
        if self.count == 1 and self.stdev is not None:
            raise WalkForwardError("count == 1 must report stdev as None (single-value dispersion is not assessable)")


@dataclass(frozen=True)
class MetricAggregate:
    """Per-metric cross-window statistics and IS-vs-OOS degradation."""

    metric: str
    is_stats: MetricStats
    oos_stats: MetricStats
    degradation: Decimal | None

    def __post_init__(self) -> None:
        if self.metric not in AGGREGATED_METRICS:
            raise WalkForwardError(f"metric {self.metric!r} is not a member of AGGREGATED_METRICS")
        if not isinstance(self.is_stats, MetricStats) or not isinstance(self.oos_stats, MetricStats):
            raise WalkForwardError("is_stats and oos_stats must be MetricStats")
        if self.degradation is not None and (not isinstance(self.degradation, Decimal) or not self.degradation.is_finite()):
            raise WalkForwardError("degradation must be None or a finite Decimal")
        if self.metric == "trade_count" and self.degradation is not None:
            raise WalkForwardError("trade_count degradation is structurally undefined and must be None")


@dataclass(frozen=True)
class WalkForwardAggregate:
    """All per-metric aggregates in canonical AGGREGATED_METRICS order."""

    period_count: int
    metrics: tuple[MetricAggregate, ...]

    def __post_init__(self) -> None:
        if type(self.period_count) is not int or self.period_count < 1:
            raise WalkForwardError("period_count must be a positive int")
        if not isinstance(self.metrics, tuple) or len(self.metrics) != len(AGGREGATED_METRICS):
            raise WalkForwardError("metrics must be a tuple of MetricAggregate with one entry per AGGREGATED_METRICS")
        for aggregate, expected in zip(self.metrics, AGGREGATED_METRICS):
            if not isinstance(aggregate, MetricAggregate):
                raise WalkForwardError("metrics entries must be MetricAggregate")
            if aggregate.metric != expected:
                raise WalkForwardError(f"metrics must be in AGGREGATED_METRICS order; expected {expected!r}, got {aggregate.metric!r}")


def _metric_stats(values: list[Decimal]) -> MetricStats:
    """Mean/median/population-stdev over defined values (Decimal-exact)."""
    count = len(values)
    if count == 0:
        return MetricStats(mean=None, median=None, stdev=None, count=0)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        mean = sum(values, Decimal("0")) / Decimal(count)
        ordered = sorted(values)
        if count % 2 == 1:
            median = ordered[count // 2]
        else:
            median = (ordered[count // 2 - 1] + ordered[count // 2]) / Decimal(2)
        stdev: Decimal | None = None
        if count >= 2:
            variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(count)
            stdev = variance.sqrt()
    return MetricStats(mean=mean, median=median, stdev=stdev, count=count)


def aggregate_periods(*, periods: tuple[WindowBacktestResult, ...]) -> WalkForwardAggregate:
    """Aggregate per-period results (pure, deterministic).

    ``periods`` must be a non-empty tuple of :class:`WindowBacktestResult`
    with strictly ascending, gap-free window indices (duplicates and
    shuffles are rejected, never reordered or deduped).
    """
    from alpha_algo_walk_forward.results import WindowBacktestResult

    if not isinstance(periods, tuple) or not periods:
        raise WalkForwardError("periods must be a non-empty tuple of WindowBacktestResult")
    if not all(isinstance(period, WindowBacktestResult) for period in periods):
        raise WalkForwardError("periods must contain only WindowBacktestResult")
    for index, period in enumerate(periods):
        if period.window.index != index:
            raise WalkForwardError("periods must be strictly ascending and gap-free (window.index must equal the position)")

    aggregates: list[MetricAggregate] = []
    for metric in AGGREGATED_METRICS:
        is_values = [getattr(period.is_metrics, metric) for period in periods]
        oos_values = [getattr(period.oos_metrics, metric) for period in periods]
        is_defined = [value for value in is_values if value is not None]
        oos_defined = [value for value in oos_values if value is not None]

        is_stats = _metric_stats([Decimal(value) for value in is_defined])
        oos_stats = _metric_stats([Decimal(value) for value in oos_defined])

        degradation: Decimal | None = None
        if metric in DEGRADATION_METRICS:
            is_mean = is_stats.mean
            oos_mean = oos_stats.mean
            if is_mean is not None and oos_mean is not None and is_mean != 0:
                direction = DEGRADATION_DIRECTIONS[metric]
                with localcontext() as ctx:
                    ctx.prec = DECIMAL_PRECISION
                    degradation = direction * (is_mean - oos_mean) / abs(is_mean)

        aggregates.append(
            MetricAggregate(metric=metric, is_stats=is_stats, oos_stats=oos_stats, degradation=degradation)
        )

    return WalkForwardAggregate(period_count=len(periods), metrics=tuple(aggregates))
