"""Typed errors for the backtesting data-quality package (P16)."""

from __future__ import annotations

__all__ = ["DataQualityError"]


class DataQualityError(ValueError):
    """Raised for out-of-contract inputs to the data-quality classifier.

    The classifier itself reports data issues as findings (never raises for
    bad *data*); it raises only for a malformed call (non-record inputs,
    invalid reference time, invalid step).
    """
