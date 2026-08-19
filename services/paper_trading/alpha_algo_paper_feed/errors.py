"""Errors for the paper market-data feed (P8-002)."""

from __future__ import annotations

__all__ = ["PaperFeedError"]


class PaperFeedError(ValueError):
    """Base error for the paper market-data feed.

    Raised for any record the feed refuses to convert. The feed never
    degrades, repairs, or defaults: incoherent input fails loud (master rules
    1/21), so a caller can never mistake a degraded conversion for real
    market data.
    """
