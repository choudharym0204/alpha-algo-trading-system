"""Typed errors for the walk-forward testing harness (P7-003).

Every refused input and every runner-contract violation raises a
:class:`WalkForwardError`; nothing is repaired, defaulted, reordered, or
silently dropped. :class:`WalkForwardMetricsError` is raised when honest
aggregation or assessment math is impossible (a non-finite carried value
that slipped past construction).
"""

from __future__ import annotations

__all__ = ["WalkForwardError", "WalkForwardMetricsError"]


class WalkForwardError(ValueError):
    """Base error: refused input or runner-contract violation."""


class WalkForwardMetricsError(WalkForwardError):
    """Raised when aggregation/assessment math is impossible."""
