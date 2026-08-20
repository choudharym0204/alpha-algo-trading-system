"""Reconciliation tolerance model (Phase 14).

Tolerances are explicit, configurable, and narrow — they model rounding/timing,
not real financial divergence. No broad tolerance that could hide a genuine
quantity/funds mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Tolerance:
    price_epsilon: Decimal = Decimal("0.0001")     # 4-dp price rounding
    fee_epsilon: Decimal = Decimal("0.01")         # fee/commission rounding
    funds_epsilon: Decimal = Decimal("0.01")       # balance rounding
    timestamp_skew_seconds: float = 300.0          # provider timing lag


def within(a: Decimal | None, b: Decimal | None, epsilon: Decimal) -> bool:
    """True when both values are present and differ by at most ``epsilon``."""
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= epsilon


def timestamps_close(
    a: datetime | None, b: datetime | None, skew_seconds: float
) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs((a - b).total_seconds()) <= skew_seconds
