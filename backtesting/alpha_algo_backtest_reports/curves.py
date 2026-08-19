"""Equity-curve derivations for backtest performance reports (P7-004).

Period returns, drawdown series, downside deviation, and period-bucketed
performance are pure functions of a :class:`BacktestRun`'s equity curve.
Every derived value is a hypothetical reconstruction of the explicit
historical inputs under documented assumptions; it is not evidence of
profitability and implies no forward performance. All arithmetic is exact
``Decimal`` under a fixed ``localcontext`` precision 28 — no float, no
``math``/``statistics`` path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum

from alpha_algo_backtest_engine import DECIMAL_PRECISION, EquityPoint

from alpha_algo_backtest_reports.errors import (
    BacktestReportError,
    BacktestReportMetricsError,
)

__all__ = [
    "DRAWDOWN_CURVE_POLICY",
    "PERIOD_BUCKET_POLICY",
    "DrawdownPoint",
    "PeriodBucket",
    "PeriodGranularity",
    "ReturnPoint",
    "bucket_performance",
    "compute_downside_deviation",
    "compute_drawdown_series",
    "compute_period_returns",
]

DRAWDOWN_CURVE_POLICY = (
    "Drawdown is the running-peak decline at each equity point: peak_0 = "
    "equity_0, peak_k = max(peak_{k-1}, equity_k), and drawdown_k = "
    "(peak_k - equity_k) / peak_k in [0, 1]. The peak never zeroes because "
    "initial capital and every marked equity stay positive."
)

PERIOD_BUCKET_POLICY = (
    "Period buckets split the equity curve contiguously on calendar-key "
    "change (daily (Y,M,D), monthly (Y,M), yearly (Y,)) using each point's "
    "own timezone wall-clock date. Bucket return is intra-bucket first-point "
    "to last-point; a single-point bucket has no return (None)."
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _validate_equity_curve(equity_curve: tuple[EquityPoint, ...]) -> None:
    if not isinstance(equity_curve, tuple) or not equity_curve:
        raise BacktestReportError("equity_curve must be a non-empty tuple of EquityPoint")
    if not all(isinstance(point, EquityPoint) for point in equity_curve):
        raise BacktestReportError("equity_curve entries must be EquityPoint")
    for point in equity_curve:
        if not isinstance(point.equity, Decimal) or not point.equity.is_finite():
            raise BacktestReportMetricsError("equity curve values must be finite Decimals")
        if point.equity <= 0:
            raise BacktestReportMetricsError("marked equity must stay positive to compute honest reports")


@dataclass(frozen=True)
class ReturnPoint:
    """One simple per-record return between consecutive equity marks.

    A return point is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """

    timestamp: datetime
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) or not _is_timezone_aware(self.timestamp):
            raise BacktestReportError("ReturnPoint.timestamp must be timezone-aware")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise BacktestReportError("ReturnPoint.value must be a finite Decimal")


@dataclass(frozen=True)
class DrawdownPoint:
    """One drawdown observation at one equity mark.

    A drawdown point is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """

    timestamp: datetime
    equity: Decimal
    peak_equity: Decimal
    drawdown_ratio: Decimal
    drawdown_amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) or not _is_timezone_aware(self.timestamp):
            raise BacktestReportError("DrawdownPoint.timestamp must be timezone-aware")
        for name, value in (
            ("equity", self.equity),
            ("peak_equity", self.peak_equity),
            ("drawdown_ratio", self.drawdown_ratio),
            ("drawdown_amount", self.drawdown_amount),
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise BacktestReportError(f"DrawdownPoint.{name} must be a finite Decimal")
        if self.equity <= 0 or self.peak_equity <= 0:
            raise BacktestReportError("DrawdownPoint equity values must be positive")
        if self.drawdown_ratio < 0 or self.drawdown_ratio > 1:
            raise BacktestReportError("DrawdownPoint.drawdown_ratio must be in [0, 1]")
        if self.drawdown_amount < 0:
            raise BacktestReportError("DrawdownPoint.drawdown_amount must be non-negative")


class PeriodGranularity(StrEnum):
    """Calendar granularity for period-bucketed performance.

    A period bucket is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


@dataclass(frozen=True)
class PeriodBucket:
    """One calendar bucket of the equity curve (intra-bucket return).

    A period bucket is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """

    label: str
    start_timestamp: datetime
    end_timestamp: datetime
    start_equity: Decimal
    end_equity: Decimal
    period_return: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise BacktestReportError("PeriodBucket.label must be a non-empty string")
        if not isinstance(self.start_timestamp, datetime) or not _is_timezone_aware(self.start_timestamp):
            raise BacktestReportError("PeriodBucket.start_timestamp must be timezone-aware")
        if not isinstance(self.end_timestamp, datetime) or not _is_timezone_aware(self.end_timestamp):
            raise BacktestReportError("PeriodBucket.end_timestamp must be timezone-aware")
        if self.start_timestamp > self.end_timestamp:
            raise BacktestReportError("PeriodBucket start must not follow end")
        for name, value in (("start_equity", self.start_equity), ("end_equity", self.end_equity)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise BacktestReportError(f"PeriodBucket.{name} must be a positive finite Decimal")
        if self.period_return is not None and (
            not isinstance(self.period_return, Decimal) or not self.period_return.is_finite()
        ):
            raise BacktestReportError("PeriodBucket.period_return must be a finite Decimal or None")


def compute_period_returns(equity_curve: tuple[EquityPoint, ...]) -> tuple[ReturnPoint, ...]:
    """Return the simple per-record returns between consecutive equity marks.

    These returns are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability. Returns an empty tuple when there are fewer than two
    points, and raises :class:`BacktestReportMetricsError` if any marked
    equity is non-positive.
    """
    _validate_equity_curve(equity_curve)
    if len(equity_curve) < 2:
        return ()
    result: list[ReturnPoint] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        for index in range(1, len(equity_curve)):
            previous = equity_curve[index - 1].equity
            current = equity_curve[index].equity
            value = (current - previous) / previous
            result.append(ReturnPoint(timestamp=equity_curve[index].timestamp, value=value))
    return tuple(result)


def compute_drawdown_series(equity_curve: tuple[EquityPoint, ...]) -> tuple[DrawdownPoint, ...]:
    """Return the running-peak drawdown series (one point per equity mark).

    The drawdown series is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability. The peak resets upward and never zeroes because equity
    stays positive. Raises :class:`BacktestReportMetricsError` on
    non-positive equity.
    """
    _validate_equity_curve(equity_curve)
    result: list[DrawdownPoint] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        peak = equity_curve[0].equity
        for point in equity_curve:
            equity = point.equity
            if equity > peak:
                peak = equity
            drawdown_amount = peak - equity
            drawdown_ratio = drawdown_amount / peak
            result.append(
                DrawdownPoint(
                    timestamp=point.timestamp,
                    equity=equity,
                    peak_equity=peak,
                    drawdown_ratio=drawdown_ratio,
                    drawdown_amount=drawdown_amount,
                )
            )
    return tuple(result)


def compute_downside_deviation(returns: tuple[Decimal, ...]) -> Decimal:
    """Return the population downside semi-deviation (target 0) of returns.

    Downside deviation is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability. The semi-deviation is ``sqrt(mean(min(r, 0) ** 2))`` over
    the full sample; it is ``Decimal("0")`` for an empty sample.
    """
    if not isinstance(returns, tuple):
        raise BacktestReportError("returns must be a tuple of Decimal")
    for value in returns:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise BacktestReportError("returns must contain only finite Decimals")
    if not returns:
        return Decimal("0")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        squares = sum((min(value, Decimal("0")) ** 2 for value in returns), Decimal("0"))
        return (squares / Decimal(len(returns))).sqrt()


def _bucket_key(timestamp: datetime, granularity: PeriodGranularity) -> tuple[int, ...]:
    if granularity is PeriodGranularity.DAILY:
        return (timestamp.year, timestamp.month, timestamp.day)
    if granularity is PeriodGranularity.MONTHLY:
        return (timestamp.year, timestamp.month)
    return (timestamp.year,)


def _bucket_label(key: tuple[int, ...]) -> str:
    if len(key) == 3:
        return f"{key[0]:04d}-{key[1]:02d}-{key[2]:02d}"
    if len(key) == 2:
        return f"{key[0]:04d}-{key[1]:02d}"
    return f"{key[0]:04d}"


def bucket_performance(
    equity_curve: tuple[EquityPoint, ...],
    *,
    granularity: PeriodGranularity,
) -> tuple[PeriodBucket, ...]:
    """Bucket the equity curve by calendar granularity (daily/monthly/yearly).

    Bucket performance is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability. Buckets are contiguous and chronological, splitting only
    on calendar-key change; a single-point bucket has a ``None`` return.
    """
    if not isinstance(granularity, PeriodGranularity):
        raise BacktestReportError("granularity must be a PeriodGranularity member")
    _validate_equity_curve(equity_curve)

    buckets: list[PeriodBucket] = []
    current_key: tuple[int, ...] | None = None
    current_points: list[EquityPoint] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        for point in equity_curve:
            key = _bucket_key(point.timestamp, granularity)
            if current_key is None:
                current_key = key
                current_points = [point]
            elif key == current_key:
                current_points.append(point)
            else:
                buckets.append(_make_bucket(current_key, current_points))
                current_key = key
                current_points = [point]
        if current_key is not None and current_points:
            buckets.append(_make_bucket(current_key, current_points))
    return tuple(buckets)


def _make_bucket(key: tuple[int, ...], points: list[EquityPoint]) -> PeriodBucket:
    start = points[0]
    end = points[-1]
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        period_return = (
            (end.equity - start.equity) / start.equity if len(points) >= 2 else None
        )
    return PeriodBucket(
        label=_bucket_label(key),
        start_timestamp=start.timestamp,
        end_timestamp=end.timestamp,
        start_equity=start.equity,
        end_equity=end.equity,
        period_return=period_return,
    )
