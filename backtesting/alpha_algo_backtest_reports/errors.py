"""Typed errors for the backtest performance report package (P7-004).

A backtest performance report is a hypothetical reconstruction of the
explicit historical inputs under documented cost, fill, and parameter
assumptions; it is not evidence of profitability and implies no forward
performance. The report never degrades, repairs, or defaults: every refused
input and every genuinely uncomputable metric raises a typed error so
callers can distinguish report contract violations from other ValueErrors.
"""

from __future__ import annotations

from alpha_algo_backtest_engine.errors import BacktestEngineError

__all__ = ["BacktestReportError", "BacktestReportMetricsError"]


class BacktestReportError(BacktestEngineError):
    """Base error: refused input or report contract violation.

    A backtest report is a hypothetical reconstruction of explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """


class BacktestReportMetricsError(BacktestReportError):
    """Raised when a report metric cannot be computed honestly.

    A report metric is a hypothetical reconstruction of explicit historical
    inputs under documented assumptions; it is not evidence of
    profitability. The report fails loud rather than fabricating a number.
    """
