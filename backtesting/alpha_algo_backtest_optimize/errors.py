"""Typed errors for the backtesting optimization package (P16)."""

from __future__ import annotations

__all__ = ["OptimizationError"]


class OptimizationError(ValueError):
    """Raised for out-of-contract inputs to grid search or Monte Carlo.

    The optimizer never silently clamps, repairs, or reorders: a malformed
    grid, an empty parameter set, a bad seed, or an out-of-range request
    raises here rather than producing a misleading result.
    """
