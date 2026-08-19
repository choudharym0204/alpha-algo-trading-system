"""Typed errors for the backtest simulation engine (P7-002).

The engine never degrades, repairs, or defaults: every refused input raises
a typed error so callers can distinguish engine contract violations from
other ValueErrors.
"""

from __future__ import annotations

__all__ = ["BacktestEngineError", "BacktestMetricsError"]


class BacktestEngineError(ValueError):
    """Base error for the backtest simulation engine.

    Raised for any input the engine refuses to simulate (non-Decimal,
    non-finite, non-positive, incoherent, or out-of-contract values). The
    engine never silently repairs, clamps, or defaults a refused input.
    """


class BacktestMetricsError(BacktestEngineError):
    """Raised when performance metrics cannot be computed honestly.

    For example when a pathological cost regime drives marked equity to or
    below zero, making return and drawdown math genuinely undefined. The
    engine fails loudly rather than fabricating a number.
    """
