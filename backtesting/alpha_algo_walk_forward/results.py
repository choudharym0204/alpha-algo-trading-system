"""Per-period execution and result storage for walk-forward testing (P7-003).

``run_walk_forward`` invokes the caller-supplied pure ``window_runner`` once
per window in ascending window-index order and stores each period's
:class:`WindowBacktestResult` independently — periods are never blended into
one run. The harness enforces what is checkable: the returned type, the
window identity (the result must echo the exact window it was handed), the
carried metric values, and the call order. Purity and slice-usage discipline
of the runner are documented caller commitments that the harness cannot
verify; determinism of the overall run therefore depends on the runner being
pure (no wall clock, no randomness, no I/O, no shared mutable state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Mapping

from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import BacktestMetrics

from alpha_algo_walk_forward.aggregate import WalkForwardAggregate, aggregate_periods
from alpha_algo_walk_forward.errors import WalkForwardError
from alpha_algo_walk_forward.windows import WalkForwardConfig, WalkForwardWindow, build_windows

__all__ = [
    "RUNNER_FAILURE_POLICY",
    "WindowBacktestResult",
    "WindowRunner",
    "WalkForwardResult",
    "run_walk_forward",
]

RUNNER_FAILURE_POLICY = (
    "Any window_runner exception aborts the walk-forward immediately: the original "
    "exception propagates unchanged, no partial aggregate is produced, and no "
    "per-period result is fabricated. There is no catch-and-continue mode."
)

# Carried fields of BacktestMetrics that aggregation consumes. BacktestMetrics
# has no __post_init__ in P7-002, so the harness validates these at its own
# boundary (defense in depth; nothing coerced, defaulted, or repaired).


def _validate_carried_metrics(metrics: BacktestMetrics, label: str) -> None:
    if not isinstance(metrics, BacktestMetrics):
        raise WalkForwardError(f"runner contract: {label} must be a BacktestMetrics")
    total_return = metrics.total_return
    if not isinstance(total_return, Decimal) or not total_return.is_finite():
        raise WalkForwardError(f"runner contract: {label}.total_return must be a finite Decimal")
    trade_count = metrics.trade_count
    if type(trade_count) is not int or trade_count < 0:
        raise WalkForwardError(f"runner contract: {label}.trade_count must be a non-negative int")
    win_rate = metrics.win_rate
    if win_rate is not None and (
        not isinstance(win_rate, Decimal) or not win_rate.is_finite() or not Decimal("0") <= win_rate <= Decimal("1")
    ):
        raise WalkForwardError(f"runner contract: {label}.win_rate must be None or a finite Decimal in [0, 1]")
    profit_factor = metrics.profit_factor
    if profit_factor is not None and (
        not isinstance(profit_factor, Decimal) or not profit_factor.is_finite() or profit_factor < 0
    ):
        raise WalkForwardError(f"runner contract: {label}.profit_factor must be None or a finite non-negative Decimal")
    max_drawdown = metrics.max_drawdown
    if not isinstance(max_drawdown, Decimal) or not max_drawdown.is_finite() or not Decimal("0") <= max_drawdown <= Decimal("1"):
        raise WalkForwardError(f"runner contract: {label}.max_drawdown must be a finite Decimal in [0, 1]")
    sharpe_ratio = metrics.sharpe_ratio
    if sharpe_ratio is not None and (not isinstance(sharpe_ratio, Decimal) or not sharpe_ratio.is_finite()):
        raise WalkForwardError(f"runner contract: {label}.sharpe_ratio must be None or a finite Decimal")


@dataclass(frozen=True)
class WindowBacktestResult:
    """One period's independently stored result.

    ``is_metrics`` must describe a backtest over exactly the window's
    in-sample records (train ∪ validation); ``oos_metrics`` must describe a
    backtest over exactly the test records. ``metadata`` is echoed only and
    never read by this package.
    """

    window: WalkForwardWindow
    is_metrics: BacktestMetrics
    oos_metrics: BacktestMetrics
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.window, WalkForwardWindow):
            raise WalkForwardError("window must be a WalkForwardWindow")
        _validate_carried_metrics(self.is_metrics, "is_metrics")
        _validate_carried_metrics(self.oos_metrics, "oos_metrics")
        if not isinstance(self.metadata, Mapping):
            raise WalkForwardError("metadata must be a Mapping")


@dataclass(frozen=True)
class WalkForwardResult:
    """The complete, immutable outcome of one walk-forward run.

    ``periods`` are stored independently, in ascending gap-free window-index
    order (duplicates and gaps are rejected, never reordered or deduped).
    Coverage metadata reports exactly how many of the parent input's records
    entered at least one window (Rule 15: unused data is visible, never
    silently deleted): ``record_count`` is the parent input size and
    ``covered_records + uncovered_records == record_count``.
    """

    config: WalkForwardConfig
    input_sha256: str
    dataset_id: str
    source: str
    periods: tuple[WindowBacktestResult, ...]
    aggregate: WalkForwardAggregate
    record_count: int
    covered_records: int
    uncovered_records: int

    def __post_init__(self) -> None:
        if not isinstance(self.config, WalkForwardConfig):
            raise WalkForwardError("config must be a WalkForwardConfig")
        for name, value in (("input_sha256", self.input_sha256), ("dataset_id", self.dataset_id), ("source", self.source)):
            if not isinstance(value, str) or not value.strip():
                raise WalkForwardError(f"{name} must be a non-empty string")
        if not isinstance(self.periods, tuple) or not self.periods:
            raise WalkForwardError("periods must be a non-empty tuple of WindowBacktestResult")
        if not all(isinstance(period, WindowBacktestResult) for period in self.periods):
            raise WalkForwardError("periods must contain only WindowBacktestResult")
        for index, period in enumerate(self.periods):
            if period.window.index != index:
                raise WalkForwardError(
                    "periods must be strictly ascending and gap-free (window.index must equal the period position)"
                )
        if not isinstance(self.aggregate, WalkForwardAggregate):
            raise WalkForwardError("aggregate must be a WalkForwardAggregate")
        if self.aggregate.period_count != len(self.periods):
            raise WalkForwardError("aggregate.period_count must equal len(periods)")
        for name, value in (
            ("record_count", self.record_count),
            ("covered_records", self.covered_records),
            ("uncovered_records", self.uncovered_records),
        ):
            if type(value) is not int or value < 0:
                raise WalkForwardError(f"{name} must be a non-negative int")
        if self.covered_records + self.uncovered_records != self.record_count:
            raise WalkForwardError("covered_records + uncovered_records must equal record_count")

    @property
    def windows(self) -> tuple[WalkForwardWindow, ...]:
        """Convenience: the windows in period order."""
        return tuple(period.window for period in self.periods)


WindowRunner = Callable[[WalkForwardWindow], WindowBacktestResult]


def run_walk_forward(
    *,
    inputs: BacktestInput,
    config: WalkForwardConfig,
    window_runner: WindowRunner,
) -> WalkForwardResult:
    """Run one deterministic walk-forward over explicit history.

    The runner is invoked exactly once per window, in ascending window-index
    order. The harness validates the returned result's type, window identity,
    and carried metric values (fail loud on violation) and lets any runner
    exception propagate unchanged. Aggregation and coverage are computed by
    the harness and stored in the returned result.
    """
    if not isinstance(inputs, BacktestInput):
        raise WalkForwardError("inputs must be a BacktestInput")
    if not isinstance(config, WalkForwardConfig):
        raise WalkForwardError("config must be a WalkForwardConfig")
    if not callable(window_runner):
        raise WalkForwardError("window_runner must be callable")

    windows = build_windows(inputs=inputs, config=config)
    periods: list[WindowBacktestResult] = []
    for window in windows:
        result = window_runner(window)
        if not isinstance(result, WindowBacktestResult):
            raise WalkForwardError(
                f"runner contract: period {window.index} returned {type(result).__name__}, expected WindowBacktestResult"
            )
        if result.window != window:
            raise WalkForwardError(
                f"runner contract: period {window.index} returned a result for a different window"
            )
        periods.append(result)

    aggregate = aggregate_periods(periods=tuple(periods))

    covered = bytearray(inputs.record_count)
    for window in windows:
        for slice_ in (window.train, window.validation, window.test):
            span = slice_.end_index - slice_.start_index
            covered[slice_.start_index : slice_.end_index] = b"\x01" * span
    covered_records = sum(covered)

    return WalkForwardResult(
        config=config,
        input_sha256=inputs.content_sha256,
        dataset_id=inputs.dataset_id,
        source=inputs.source,
        periods=tuple(periods),
        aggregate=aggregate,
        record_count=inputs.record_count,
        covered_records=covered_records,
        uncovered_records=inputs.record_count - covered_records,
    )
