from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from alpha_algo_backtest_engine import BacktestRun, CostModel, EquityPoint

from alpha_algo_backtesting import BacktestTradingMode

from alpha_algo_backtest_reports import (
    BacktestReportError,
    RiskMetrics,
    build_report,
    compute_calmar_ratio,
    compute_period_returns,
    compute_risk_metrics,
    compute_sortino_ratio,
)


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def pt(ts: datetime, equity: str) -> EquityPoint:
    return EquityPoint(timestamp=ts, equity=Decimal(equity))


def curve(equities: tuple[str, ...]) -> tuple[EquityPoint, ...]:
    return tuple(pt(utc(2026, 1, 1, 9, 0, index), equity) for index, equity in enumerate(equities))


def returns_of(equities: tuple[str, ...]) -> tuple[Decimal, ...]:
    return tuple(point.value for point in compute_period_returns(curve(equities)))


def run_with_curve(equities: tuple[str, ...]) -> object:
    c = curve(equities)
    return BacktestRun(
        mode=BacktestTradingMode.BACKTEST,
        input_sha256="a" * 64,
        dataset_id="ds",
        source="unit",
        initial_capital=c[0].equity,
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        intents=(),
        outcomes=(),
        trades=(),
        equity_curve=c,
    )


class TestSortino:
    def test_sortino_negative_closed_form(self) -> None:
        result = compute_sortino_ratio(returns_of(("100", "100", "90", "90")), risk_free_rate_per_period=Decimal("0"))
        assert result is not None
        assert abs(result - (-(Decimal("1") / Decimal("3")).sqrt())) < Decimal("1E-25")

    def test_sortino_positive_closed_form(self) -> None:
        result = compute_sortino_ratio(returns_of(("100", "125", "100")), risk_free_rate_per_period=Decimal("0"))
        assert result is not None
        assert abs(result - Decimal("2").sqrt() / Decimal("8")) < Decimal("1E-25")

    def test_sortino_no_downside_none(self) -> None:
        result = compute_sortino_ratio(returns_of(("100", "100", "110", "110")), risk_free_rate_per_period=Decimal("0"))
        assert result is None

    def test_sortino_flat_equity_none(self) -> None:
        result = compute_sortino_ratio(returns_of(("100", "100", "100")), risk_free_rate_per_period=Decimal("0"))
        assert result is None

    def test_sortino_single_return_none(self) -> None:
        result = compute_sortino_ratio(returns_of(("100", "110")), risk_free_rate_per_period=Decimal("0"))
        assert result is None

    def test_sortino_uses_risk_free_rate(self) -> None:
        returns = returns_of(("100", "100", "90", "90"))
        r0 = compute_sortino_ratio(returns, risk_free_rate_per_period=Decimal("0"))
        r1 = compute_sortino_ratio(returns, risk_free_rate_per_period=Decimal("0.01"))
        assert r0 is not None and r1 is not None
        assert r1 < r0


class TestCalmar:
    def test_calmar_formula(self) -> None:
        assert compute_calmar_ratio(total_return=Decimal("0.1"), max_drawdown=Decimal("0.25")) == Decimal("0.4")

    def test_calmar_max_drawdown_zero_none(self) -> None:
        assert compute_calmar_ratio(total_return=Decimal("0.2"), max_drawdown=Decimal("0")) is None

    def test_calmar_negative_total_return(self) -> None:
        assert compute_calmar_ratio(total_return=Decimal("-0.2"), max_drawdown=Decimal("0.2")) == Decimal("-1")

    def test_calmar_rejects_out_of_range_drawdown(self) -> None:
        with pytest.raises(BacktestReportError):
            compute_calmar_ratio(total_return=Decimal("0.1"), max_drawdown=Decimal("1.1"))
        with pytest.raises(BacktestReportError):
            compute_calmar_ratio(total_return=Decimal("0.1"), max_drawdown=Decimal("-0.1"))


class TestComputeRiskMetrics:
    def test_matches_report_risk(self) -> None:
        run = run_with_curve(("100", "120", "90", "110"))
        result = compute_risk_metrics(run, risk_free_rate_per_period=Decimal("0"))
        assert isinstance(result, RiskMetrics)
        assert result.calmar_ratio == Decimal("0.4")
        assert result.sortino_ratio is not None

    def test_non_positive_equity_raises(self) -> None:
        with pytest.raises(BacktestReportError):
            compute_risk_metrics(run_with_curve(("100000", "0")), risk_free_rate_per_period=Decimal("0"))

    def test_rejects_non_backtest_run(self) -> None:
        with pytest.raises(BacktestReportError):
            compute_risk_metrics(None, risk_free_rate_per_period=Decimal("0"))  # type: ignore[arg-type]


class TestReportRiskWiring:
    def test_report_risk_metrics_present(self) -> None:
        report = build_report(run_with_curve(("100", "120", "90", "110")), risk_free_rate_per_period=Decimal("0"))
        assert report.risk.calmar_ratio == Decimal("0.4")
        assert report.risk.sortino_ratio is not None

    def test_non_positive_equity_raises_report_error(self) -> None:
        with pytest.raises(BacktestReportError):
            build_report(run_with_curve(("100000", "0")), risk_free_rate_per_period=Decimal("0"))

    def test_rejects_non_backtest_run(self) -> None:
        with pytest.raises(BacktestReportError):
            build_report(None, risk_free_rate_per_period=Decimal("0"))  # type: ignore[arg-type]

    def test_rejects_non_decimal_rf(self) -> None:
        with pytest.raises(BacktestReportError):
            build_report(run_with_curve(("100", "110")), risk_free_rate_per_period=0.01)  # type: ignore[arg-type]

    def test_rejects_negative_and_nonfinite_rf(self) -> None:
        with pytest.raises(BacktestReportError):
            build_report(run_with_curve(("100", "110")), risk_free_rate_per_period=Decimal("-0.01"))
        with pytest.raises(BacktestReportError):
            build_report(run_with_curve(("100", "110")), risk_free_rate_per_period=Decimal("Infinity"))
