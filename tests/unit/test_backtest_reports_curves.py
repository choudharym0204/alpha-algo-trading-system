from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from alpha_algo_backtest_engine import EquityPoint

from alpha_algo_backtest_reports import (
    BacktestReportError,
    PeriodGranularity,
    bucket_performance,
    compute_drawdown_series,
    compute_period_returns,
)


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def pt(ts: datetime, equity: str) -> EquityPoint:
    return EquityPoint(timestamp=ts, equity=Decimal(equity))


def curve(equities: tuple[str, ...]) -> tuple[EquityPoint, ...]:
    return tuple(pt(utc(2026, 1, 1, 9, 0, index), equity) for index, equity in enumerate(equities))


class TestDrawdownSeries:
    def test_peak_trough(self) -> None:
        c = curve(("100", "120", "90", "120"))
        result = compute_drawdown_series(c)
        assert [d.peak_equity for d in result] == [Decimal("100"), Decimal("120"), Decimal("120"), Decimal("120")]
        assert [d.drawdown_ratio for d in result] == [Decimal("0"), Decimal("0"), Decimal("0.25"), Decimal("0")]
        assert [d.drawdown_amount for d in result] == [Decimal("0"), Decimal("0"), Decimal("30"), Decimal("0")]

    def test_peak_reset(self) -> None:
        c = curve(("100", "110", "105", "120", "115", "125"))
        result = compute_drawdown_series(c)
        assert [d.drawdown_ratio for d in result] == [
            Decimal("0"),
            Decimal("0"),
            Decimal("5") / Decimal("110"),
            Decimal("0"),
            Decimal("5") / Decimal("120"),
            Decimal("0"),
        ]

    def test_monotonic_zero(self) -> None:
        result = compute_drawdown_series(curve(("100", "110", "120")))
        assert all(d.drawdown_ratio == Decimal("0") for d in result)

    def test_single_point(self) -> None:
        result = compute_drawdown_series(curve(("100",)))
        assert len(result) == 1
        assert result[0].drawdown_ratio == Decimal("0")

    def test_length_equals_equity_curve(self) -> None:
        c = curve(("100", "120", "90", "120"))
        assert len(compute_drawdown_series(c)) == len(c)

    def test_amount_and_ratio_agree(self) -> None:
        result = compute_drawdown_series(curve(("100", "120", "90", "120")))
        trough = result[2]
        assert trough.drawdown_amount == trough.peak_equity - trough.equity
        assert trough.drawdown_ratio == trough.drawdown_amount / trough.peak_equity


class TestPeriodReturns:
    def test_returns_length_and_values(self) -> None:
        c = curve(("100", "120", "90", "120"))
        result = compute_period_returns(c)
        assert len(result) == 3
        assert result[0].value == Decimal("0.2")
        assert result[1].value == Decimal("-0.25")

    def test_single_point_no_returns(self) -> None:
        assert compute_period_returns(curve(("100",))) == ()

    def test_returns_use_next_timestamp(self) -> None:
        c = (pt(utc(2026, 1, 1, 9, 0), "100"), pt(utc(2026, 1, 1, 9, 5), "110"))
        result = compute_period_returns(c)
        assert result[0].timestamp == utc(2026, 1, 1, 9, 5)


class TestBucketPerformance:
    def test_daily_same_day(self) -> None:
        c = (pt(utc(2026, 1, 1, 9, 0), "100"), pt(utc(2026, 1, 1, 10, 0), "110"))
        buckets = bucket_performance(c, granularity=PeriodGranularity.DAILY)
        assert len(buckets) == 1
        assert buckets[0].period_return == Decimal("0.1")

    def test_daily_cross_day(self) -> None:
        c = (
            pt(utc(2026, 1, 1, 9, 0), "100"),
            pt(utc(2026, 1, 2, 9, 0), "110"),
            pt(utc(2026, 1, 2, 10, 0), "121"),
        )
        buckets = bucket_performance(c, granularity=PeriodGranularity.DAILY)
        assert len(buckets) == 2
        assert buckets[0].label == "2026-01-01"
        assert buckets[1].label == "2026-01-02"
        assert buckets[1].period_return == Decimal("0.1")

    def test_monthly_buckets(self) -> None:
        c = (pt(utc(2026, 1, 31, 23, 0), "100"), pt(utc(2026, 2, 1, 0, 1), "110"))
        buckets = bucket_performance(c, granularity=PeriodGranularity.MONTHLY)
        assert len(buckets) == 2
        assert buckets[0].label == "2026-01"
        assert buckets[1].label == "2026-02"

    def test_yearly_buckets(self) -> None:
        c = (pt(utc(2025, 12, 31, 23, 59), "100"), pt(utc(2026, 1, 1, 0, 1), "110"))
        buckets = bucket_performance(c, granularity=PeriodGranularity.YEARLY)
        assert len(buckets) == 2
        assert buckets[0].label == "2025"
        assert buckets[1].label == "2026"

    def test_bucket_return_uses_first_and_last(self) -> None:
        c = (pt(utc(2026, 1, 1, 9, 0), "100"), pt(utc(2026, 1, 1, 9, 1), "105"), pt(utc(2026, 1, 1, 9, 2), "110"))
        buckets = bucket_performance(c, granularity=PeriodGranularity.DAILY)
        assert buckets[0].period_return == Decimal("0.1")

    def test_single_point_bucket_none(self) -> None:
        c = (pt(utc(2026, 1, 1, 9, 0), "100"),)
        buckets = bucket_performance(c, granularity=PeriodGranularity.DAILY)
        assert buckets[0].period_return is None

    def test_granularity_members(self) -> None:
        assert [m.value for m in PeriodGranularity] == ["DAILY", "MONTHLY", "YEARLY"]

    def test_invalid_granularity_raises(self) -> None:
        c = curve(("100", "110"))
        with pytest.raises(BacktestReportError):
            bucket_performance(c, granularity="weekly")  # type: ignore[arg-type]
        with pytest.raises(BacktestReportError):
            bucket_performance(c, granularity=None)  # type: ignore[arg-type]

    def test_ordering_deterministic(self) -> None:
        c = (
            pt(utc(2026, 1, 1, 9, 0), "100"),
            pt(utc(2026, 1, 2, 9, 0), "110"),
            pt(utc(2026, 1, 3, 9, 0), "105"),
        )
        buckets = bucket_performance(c, granularity=PeriodGranularity.DAILY)
        assert [b.label for b in buckets] == ["2026-01-01", "2026-01-02", "2026-01-03"]
