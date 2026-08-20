"""Typed errors for the backtesting advanced-analytics package (P16).

The analytics package never degrades, repairs, or defaults: every refused
input raises a typed error so callers can distinguish a contract violation
from an undefined metric (which is returned as ``None``, never fabricated).
"""

from __future__ import annotations

__all__ = [
    "AnalyticsError",
    "AnnualizationError",
    "ExcursionError",
    "RiskMeasureError",
]


class AnalyticsError(ValueError):
    """Base error for the advanced-analytics package.

    Raised for any input the analytics refuse to compute on (mismatched
    series lengths, non-positive capital denominators, out-of-range
    confidence, malformed price paths). Undefined-but-valid metrics are
    returned as ``None`` — errors are reserved for contract violations.
    """


class AnnualizationError(AnalyticsError):
    """Raised when CAGR cannot be computed honestly.

    For example a non-positive beginning or ending capital (return math is
    genuinely undefined there) or a non-positive annualization basis.
    """


class RiskMeasureError(AnalyticsError):
    """Raised when VaR/CVaR or Alpha/Beta inputs are out of contract."""


class ExcursionError(AnalyticsError):
    """Raised when a trade excursion (MFE/MAE) cannot be computed honestly."""
