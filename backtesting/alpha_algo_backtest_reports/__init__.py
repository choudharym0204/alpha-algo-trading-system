"""Backtest performance reports (P7-004).

A pure, deterministic report generator composing the verified P7-001
foundation and P7-002 engine: it reconstructs extended trade statistics,
non-annualized risk ratios, a drawdown curve, and period-bucketed
performance from a single explicit :class:`BacktestRun` and an injected
per-period risk-free rate. Reports are hypothetical reconstructions of the
explicit historical inputs under documented cost, fill, and parameter
assumptions; they are not evidence of profitability and imply no forward
performance. This package performs no execution, no persistence, no regime
analysis, no signal/strategy runtime, and no live/broker surface.
``LIVE_TRADING_ENABLED=false`` stays and all 17 LIVE safety gates remain
TODO.

Fixed, auditable policy constants (breaking any of these is a contract
change, not an implementation detail — the ADR-0008/0009/0010 precedent):
``DRAWDOWN_CURVE_POLICY``, ``PERIOD_BUCKET_POLICY``, ``RISK_METRICS_POLICY``,
``TRADE_STATISTICS_POLICY``, ``REPORT_SCOPE_POLICY``,
``TRADE_RECONSTRUCTION_POLICY``, plus the fixed ``REPORT_LIMITATIONS``
honesty metadata. ``DECIMAL_PRECISION`` (28) is imported from the engine —
single source of truth.
"""

from __future__ import annotations

from alpha_algo_backtest_engine import DECIMAL_PRECISION

from alpha_algo_backtest_reports.curves import (
    DRAWDOWN_CURVE_POLICY,
    PERIOD_BUCKET_POLICY,
    DrawdownPoint,
    PeriodBucket,
    PeriodGranularity,
    ReturnPoint,
    bucket_performance,
    compute_downside_deviation,
    compute_drawdown_series,
    compute_period_returns,
)
from alpha_algo_backtest_reports.errors import BacktestReportError, BacktestReportMetricsError
from alpha_algo_backtest_reports.report import (
    REPORT_LIMITATIONS,
    REPORT_SCOPE_POLICY,
    TRADE_RECONSTRUCTION_POLICY,
    BacktestReport,
    TradeReconstruction,
    build_report,
    build_trade_reconstructions,
)
from alpha_algo_backtest_reports.risk import (
    RISK_METRICS_POLICY,
    RiskMetrics,
    compute_calmar_ratio,
    compute_risk_metrics,
    compute_sortino_ratio,
)
from alpha_algo_backtest_reports.statistics import (
    TRADE_STATISTICS_POLICY,
    TradeStatistics,
    compute_trade_statistics,
)

__all__ = [
    "DECIMAL_PRECISION",
    "DRAWDOWN_CURVE_POLICY",
    "PERIOD_BUCKET_POLICY",
    "REPORT_LIMITATIONS",
    "REPORT_SCOPE_POLICY",
    "RISK_METRICS_POLICY",
    "TRADE_RECONSTRUCTION_POLICY",
    "TRADE_STATISTICS_POLICY",
    "BacktestReport",
    "BacktestReportError",
    "BacktestReportMetricsError",
    "DrawdownPoint",
    "PeriodBucket",
    "PeriodGranularity",
    "ReturnPoint",
    "RiskMetrics",
    "TradeReconstruction",
    "TradeStatistics",
    "bucket_performance",
    "build_report",
    "build_trade_reconstructions",
    "compute_calmar_ratio",
    "compute_downside_deviation",
    "compute_drawdown_series",
    "compute_period_returns",
    "compute_risk_metrics",
    "compute_sortino_ratio",
    "compute_trade_statistics",
]
