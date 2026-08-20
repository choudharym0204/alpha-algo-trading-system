"""Typed errors for the backtesting portfolio simulation package (P16)."""

from __future__ import annotations

__all__ = ["PortfolioBacktestError"]


class PortfolioBacktestError(ValueError):
    """Raised for out-of-contract inputs to the multi-symbol portfolio sim.

    The portfolio simulator never degrades, repairs, or defaults: duplicate
    symbols, empty universes, invalid allocations, and incoherent intents
    raise here rather than producing a misleading result.
    """
