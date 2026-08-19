"""Walk-forward testing harness (P7-003).

A pure window scheduler + aggregation + overfitting assessment composing the
verified P7-001 foundation (``BacktestInput``) and the P7-002 backtest
simulation engine (``BacktestMetrics``, ``DECIMAL_PRECISION``). Walk-forward
results are hypothetical reconstructions of the explicit historical inputs
under documented window, cost, and runner assumptions; they are not evidence
of profitability and imply no forward performance.

Fixed, auditable policy constants (breaking any of these is a contract
change, not an implementation detail - the ADR-0008/0009 precedent):

- ``DECIMAL_PRECISION`` (28, imported from the engine - single source of truth)
- ``WINDOW_SCHEDULE_POLICY``: count-based uniform rolling windows; strictly
  forward and strictly disjoint within a window; step >= test so OOS windows
  never overlap; trailing remainder unused, never truncated, visible in
  coverage metadata
- ``METRIC_AGGREGATION_POLICY``: Decimal-exact mean/median/population-stdev
  per core metric; IS-vs-OOS degradation on the five scale-free metrics only;
  undefined values are None, never 0/Infinity/crash
- ``OVERFITTING_FLAG_POLICY``: fixed-threshold informational flags with a
  LOW/MEDIUM/HIGH composite; no auto-reject; degenerate inputs cap at LOW
  with explicit reasons
- Thresholds: ``DEGRADATION_THRESHOLD`` (0.5), ``LOW_TRADE_COUNT_THRESHOLD``
  (30), ``MAX_RETURN_SANITY_BOUND`` (100), ``DEPENDENCY_CV_THRESHOLD`` (1.0),
  ``MIN_PERIODS_FOR_ASSESSMENT`` (3)

The ``window_runner`` is caller-supplied and MUST be pure (no wall clock, no
randomness, no I/O, no shared mutable state): the harness validates the
returned shape, window identity, and carried metric values, but purity and
fitting discipline are documented caller commitments. The harness performs
no strategy fitting, no signal generation, no parameter optimization, no
reports, and no persistence (results are in-memory and caller-owned).
"""

from __future__ import annotations

from alpha_algo_backtest_engine import DECIMAL_PRECISION

from alpha_algo_walk_forward.aggregate import (
    AGGREGATED_METRICS,
    DEGRADATION_DIRECTIONS,
    DEGRADATION_METRICS,
    METRIC_AGGREGATION_POLICY,
    MetricAggregate,
    MetricStats,
    WalkForwardAggregate,
    aggregate_periods,
)
from alpha_algo_walk_forward.assessment import (
    DEGRADATION_THRESHOLD,
    DEPENDENCY_CV_THRESHOLD,
    LOW_TRADE_COUNT_THRESHOLD,
    MAX_RETURN_SANITY_BOUND,
    MIN_PERIODS_FOR_ASSESSMENT,
    OVERFITTING_FLAG_NAMES,
    OVERFITTING_FLAG_POLICY,
    OverfittingAssessment,
    OverfittingFlag,
    OverfittingRisk,
    assess_overfitting,
)
from alpha_algo_walk_forward.errors import WalkForwardError, WalkForwardMetricsError
from alpha_algo_walk_forward.results import (
    RUNNER_FAILURE_POLICY,
    WalkForwardResult,
    WindowBacktestResult,
    WindowRunner,
    run_walk_forward,
)
from alpha_algo_walk_forward.windows import (
    WINDOW_SCHEDULE_POLICY,
    WalkForwardConfig,
    WalkForwardWindow,
    WindowSlice,
    build_windows,
)

__all__ = [
    "AGGREGATED_METRICS",
    "DECIMAL_PRECISION",
    "DEGRADATION_DIRECTIONS",
    "DEGRADATION_METRICS",
    "DEGRADATION_THRESHOLD",
    "DEPENDENCY_CV_THRESHOLD",
    "LOW_TRADE_COUNT_THRESHOLD",
    "MAX_RETURN_SANITY_BOUND",
    "METRIC_AGGREGATION_POLICY",
    "MIN_PERIODS_FOR_ASSESSMENT",
    "OVERFITTING_FLAG_NAMES",
    "OVERFITTING_FLAG_POLICY",
    "OverfittingAssessment",
    "OverfittingFlag",
    "OverfittingRisk",
    "RUNNER_FAILURE_POLICY",
    "WINDOW_SCHEDULE_POLICY",
    "WalkForwardAggregate",
    "WalkForwardConfig",
    "WalkForwardError",
    "WalkForwardMetricsError",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WindowBacktestResult",
    "WindowRunner",
    "WindowSlice",
    "aggregate_periods",
    "assess_overfitting",
    "build_windows",
    "run_walk_forward",
]
