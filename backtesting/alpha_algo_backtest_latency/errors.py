"""Typed errors for the backtesting latency package (P16)."""

from __future__ import annotations

__all__ = ["LatencyError"]


class LatencyError(ValueError):
    """Raised for out-of-contract latency-model inputs.

    A negative delay, a malformed intent, or an incoherent latency model
    raises here rather than silently clamping.
    """
