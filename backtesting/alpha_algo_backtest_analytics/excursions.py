"""Maximum Favorable / Adverse Excursion (MFE / MAE) per trade (P16).

MFE and MAE measure, for a completed trade, the best and worst mark-to-market
excursion observed between entry and exit. They are **post-trade analytics**:
the observation window is ``(entry, exit]`` — records strictly after entry up
to and including the exit record — so no information beyond the trade close
ever leaks into the calculation. They are not a strategy input and never
influence fills or signals.

Price source: the caller supplies the replayed per-symbol price path as
``ExcursionPricePoint`` (``high`` / ``low`` per observation). For candle
inputs ``high``/``low`` are the candle extremes; for tick inputs both are the
last traded price. Using intrabar extremes for excursions is legitimate here
because the metric is computed only after the trade is closed.

Long semantics: favorable = price above entry, adverse = price below entry.
Short semantics are the mirror. ``mfe >= 0`` and ``mae <= 0`` always.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from alpha_algo_backtest_analytics.errors import ExcursionError

__all__ = [
    "EXCURSION_POLICY",
    "ExcursionPoint",
    "ExcursionSide",
    "ExcursionResult",
    "compute_excursions",
]


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


class ExcursionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


EXCURSION_POLICY = (
    "MFE/MAE are post-trade analytics over the (entry, exit] price path. "
    "LONG: mfe = max(0, max(highs + exit) - entry), mae = min(0, min(lows + "
    "exit) - entry). SHORT mirrors (entry - lows / entry - highs). mfe >= 0, "
    "mae <= 0. No data beyond the trade close is observed."
)


@dataclass(frozen=True)
class ExcursionPoint:
    """One replayed price observation (high/low extremes) for one symbol."""

    timestamp: datetime
    high: Decimal
    low: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) or not _is_timezone_aware(self.timestamp):
            raise ExcursionError("ExcursionPoint.timestamp must be timezone-aware")
        for name, value in (("high", self.high), ("low", self.low)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ExcursionError(f"ExcursionPoint.{name} must be a positive finite Decimal")
        if self.low > self.high:
            raise ExcursionError("ExcursionPoint.low must not exceed high")


@dataclass(frozen=True)
class ExcursionResult:
    """MFE and MAE for one completed trade.

    These are informational reconstructions of the explicit historical
    inputs under the documented method; they imply no forward performance.
    """

    side: ExcursionSide
    entry_price: Decimal
    exit_price: Decimal
    observation_count: int
    mfe: Decimal
    mae: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.side, ExcursionSide):
            raise ExcursionError("side must be an ExcursionSide member")
        for name, value in (("entry_price", self.entry_price), ("exit_price", self.exit_price)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ExcursionError(f"{name} must be a positive finite Decimal")
        if type(self.observation_count) is not int or self.observation_count < 0:
            raise ExcursionError("observation_count must be a non-negative int")
        if not isinstance(self.mfe, Decimal) or not self.mfe.is_finite() or self.mfe < 0:
            raise ExcursionError("mfe must be a non-negative finite Decimal")
        if not isinstance(self.mae, Decimal) or not self.mae.is_finite() or self.mae > 0:
            raise ExcursionError("mae must be a non-positive finite Decimal")


def compute_excursions(
    *,
    side: ExcursionSide,
    entry_timestamp: datetime,
    exit_timestamp: datetime,
    entry_price: Decimal,
    exit_price: Decimal,
    path: tuple[ExcursionPoint, ...],
) -> ExcursionResult:
    """Compute MFE and MAE over the ``(entry, exit]`` price path.

    The observation window is strictly after ``entry_timestamp`` and up to
    and including ``exit_timestamp`` (``exit_price`` is always included as an
    observation, so an empty path still yields ``mfe = max(0, exit-entry)``
    for a long). Raises :class:`ExcursionError` on malformed inputs.
    """
    if not isinstance(side, ExcursionSide):
        raise ExcursionError("side must be an ExcursionSide member")
    for name, value in (("entry_timestamp", entry_timestamp), ("exit_timestamp", exit_timestamp)):
        if not isinstance(value, datetime) or not _is_timezone_aware(value):
            raise ExcursionError(f"{name} must be timezone-aware")
    if entry_timestamp > exit_timestamp:
        raise ExcursionError("entry_timestamp must not follow exit_timestamp")
    for name, value in (("entry_price", entry_price), ("exit_price", exit_price)):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ExcursionError(f"{name} must be a positive finite Decimal")
    if not isinstance(path, tuple) or not all(isinstance(point, ExcursionPoint) for point in path):
        raise ExcursionError("path must be a tuple of ExcursionPoint")

    highs: list[Decimal] = [exit_price]
    lows: list[Decimal] = [exit_price]
    for point in path:
        if point.timestamp <= entry_timestamp:
            continue
        if point.timestamp > exit_timestamp:
            continue
        highs.append(point.high)
        lows.append(point.low)

    observation_count = len(path)

    if side is ExcursionSide.LONG:
        mfe = max(highs) - entry_price
        mae = min(lows) - entry_price
    else:
        mfe = entry_price - min(lows)
        mae = entry_price - max(highs)

    # Clamp: mfe is favorable (>= 0), mae is adverse (<= 0). The clamp is a
    # guard against a pathological price path; with a correct path the raw
    # value already respects the sign, but we never emit an out-of-contract
    # result.
    if mfe < 0:
        mfe = Decimal("0")
    if mae > 0:
        mae = Decimal("0")

    return ExcursionResult(
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        observation_count=observation_count,
        mfe=mfe,
        mae=mae,
    )
