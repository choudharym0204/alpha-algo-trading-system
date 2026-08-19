from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from dataclasses import FrozenInstanceError

from alpha_algo_contracts import MarketTick
from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import BacktestMetrics
from alpha_algo_walk_forward import (
    DEGRADATION_THRESHOLD,
    DEPENDENCY_CV_THRESHOLD,
    LOW_TRADE_COUNT_THRESHOLD,
    MAX_RETURN_SANITY_BOUND,
    MIN_PERIODS_FOR_ASSESSMENT,
    OVERFITTING_FLAG_NAMES,
    OVERFITTING_FLAG_POLICY,
    OverfittingAssessment,
    OverfittingRisk,
    WalkForwardConfig,
    WalkForwardError,
    WindowBacktestResult,
    aggregate_periods,
    assess_overfitting,
    build_windows,
)

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
UTC = timezone.utc


def utc(y, mo, d, h=9, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def tick(ts: datetime) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal("100"),
        bid=Decimal("99.5"),
        ask=Decimal("100.5"),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def _input(record_count: int) -> BacktestInput:
    records = tuple(tick(utc(2026, 1, 2, 9, 0) + timedelta(minutes=i)) for i in range(record_count))
    return BacktestInput(dataset_id="ds", source="unit", records=records)


def _metrics(total_return, trade_count=50, win_rate=Decimal("0.6"), profit_factor=Decimal("1.5"), max_drawdown=Decimal("0.1"), sharpe_ratio=Decimal("0.5")):
    return BacktestMetrics(
        initial_capital=Decimal("100000"),
        final_equity=Decimal("100000"),
        total_return=total_return if isinstance(total_return, Decimal) else Decimal(str(total_return)),
        trade_count=trade_count,
        wins=30,
        losses=20,
        breakevens=0,
        win_rate=win_rate,
        gross_profit=Decimal("1500"),
        gross_loss=Decimal("1000"),
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        risk_free_rate_per_period=Decimal("0"),
    )


def _windows(count: int):
    inputs = _input(60)
    config = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)
    return build_windows(inputs=inputs, config=config)[:count]


def _periods(count: int, *, oos_returns, is_returns=None, oos_trades=None, oos_max_drawdown=None, oos_sharpe=None, is_sharpe=None):
    windows = _windows(count)
    periods = []
    for k in range(count):
        is_metrics = _metrics(
            is_returns[k] if is_returns is not None else Decimal("0.10"),
            trade_count=80,
            sharpe_ratio=is_sharpe[k] if is_sharpe is not None else Decimal("0.5"),
        )
        kwargs = {}
        if oos_trades is not None:
            kwargs["trade_count"] = oos_trades[k]
        if oos_max_drawdown is not None:
            kwargs["max_drawdown"] = oos_max_drawdown[k]
        if oos_sharpe is not None:
            kwargs["sharpe_ratio"] = oos_sharpe[k]
        oos_metrics = _metrics(oos_returns[k], **kwargs)
        periods.append(WindowBacktestResult(window=windows[k], is_metrics=is_metrics, oos_metrics=oos_metrics))
    return tuple(periods)


def _assess(count: int, *, oos_returns, **kwargs) -> OverfittingAssessment:
    periods = _periods(count, oos_returns=oos_returns, **kwargs)
    return assess_overfitting(periods=periods, aggregate=aggregate_periods(periods=periods))


def _flag(assessment: OverfittingAssessment, name: str):
    return next(flag for flag in assessment.flags if flag.name == name)


class TestDegradationFlags:
    def test_degradation_flag_triggers_above_threshold(self) -> None:
        # (0.10 - 0.049) / 0.10 = 0.51 > 0.5
        assessment = _assess(3, oos_returns=[0.049, 0.049, 0.049])
        assert _flag(assessment, "degradation_total_return").triggered

    def test_degradation_exactly_at_threshold_no_flag(self) -> None:
        # Strict >: 0.50 exactly must not trigger.
        assessment = _assess(3, oos_returns=[0.05, 0.05, 0.05])
        assert not _flag(assessment, "degradation_total_return").triggered

    def test_degradation_below_threshold_no_flag(self) -> None:
        assessment = _assess(3, oos_returns=[0.06, 0.06, 0.06])
        assert not _flag(assessment, "degradation_total_return").triggered

    def test_degradation_undefined_no_flag_no_crash(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10], is_returns=[0.00, 0.00, 0.00])
        assert not _flag(assessment, "degradation_total_return").triggered
        assert any("degradation not assessable for total_return" in reason for reason in assessment.reasons)

    def test_degradation_flags_are_high_severity(self) -> None:
        assessment = _assess(3, oos_returns=[0.049, 0.049, 0.049])
        assert _flag(assessment, "degradation_total_return").severity is OverfittingRisk.HIGH

    def test_all_five_degradation_flags_present(self) -> None:
        assessment = _assess(3, oos_returns=[0.049, 0.049, 0.049])
        for metric in ("total_return", "win_rate", "profit_factor", "max_drawdown", "sharpe_ratio"):
            flag = _flag(assessment, f"degradation_{metric}")
            assert flag.name in OVERFITTING_FLAG_NAMES
            # win_rate/profit_factor/sharpe/max_drawdown: IS and OOS identical -> degradation 0 -> no trigger
            assert isinstance(flag.triggered, bool)


class TestOtherFlags:
    def test_low_trade_count_flag(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10], oos_trades=[3, 4, 3])
        assert _flag(assessment, "low_oos_trade_count").triggered
        assert _flag(assessment, "low_oos_trade_count").severity is OverfittingRisk.MEDIUM

    def test_low_trade_count_boundary_no_flag(self) -> None:
        # Strict <: mean exactly 30 must not trigger.
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10], oos_trades=[30, 30, 30])
        assert not _flag(assessment, "low_oos_trade_count").triggered

    def test_unrealistic_return_flag(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 150.0, 0.10])
        assert _flag(assessment, "unrealistic_oos_return").triggered
        assert _flag(assessment, "unrealistic_oos_return").severity is OverfittingRisk.HIGH

    def test_unrealistic_return_boundary_no_flag(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 100.0, 0.10])
        assert not _flag(assessment, "unrealistic_oos_return").triggered

    def test_high_period_dependency_flag(self) -> None:
        # returns [0.01, 0.31, 0.01]: mean 0.11, variance 0.02, stdev ~0.1414, CV ~1.286 > 1.0
        assessment = _assess(3, oos_returns=[0.01, 0.31, 0.01])
        assert _flag(assessment, "high_period_dependency").triggered
        assert _flag(assessment, "high_period_dependency").severity is OverfittingRisk.MEDIUM

    def test_high_period_dependency_below_threshold_no_flag(self) -> None:
        # returns [0.05, 0.35, 0.05]: mean 0.15, stdev ~0.1414, CV ~0.943 < 1.0
        assessment = _assess(3, oos_returns=[0.05, 0.35, 0.05])
        assert not _flag(assessment, "high_period_dependency").triggered

    def test_high_period_dependency_mean_non_positive_not_assessable(self) -> None:
        # mean 0 -> CV undefined -> no flag, no crash.
        assessment = _assess(3, oos_returns=[-0.20, 0.10, 0.10])
        assert not _flag(assessment, "high_period_dependency").triggered


class TestRiskMapping:
    def test_risk_mapping_low(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10])
        assert assessment.overfitting_risk is OverfittingRisk.LOW
        assert any("no overfitting flags triggered" in reason for reason in assessment.reasons)

    def test_risk_mapping_medium(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10], oos_trades=[3, 4, 3])
        assert assessment.overfitting_risk is OverfittingRisk.MEDIUM

    def test_risk_mapping_high(self) -> None:
        assessment = _assess(
            3,
            oos_returns=[0.049, 0.049, 0.049],
            oos_trades=[3, 4, 3],
            oos_max_drawdown=[Decimal("0.16"), Decimal("0.16"), Decimal("0.16")],
        )
        assert assessment.overfitting_risk is OverfittingRisk.HIGH

    def test_degradation_alone_is_high(self) -> None:
        assessment = _assess(3, oos_returns=[0.049, 0.049, 0.049])
        assert assessment.overfitting_risk is OverfittingRisk.HIGH

    def test_no_auto_reject_semantics(self) -> None:
        assessment = _assess(
            3,
            oos_returns=[0.049, 0.049, 0.049],
            oos_trades=[3, 4, 3],
            oos_max_drawdown=[Decimal("0.16"), Decimal("0.16"), Decimal("0.16")],
        )
        assert assessment.overfitting_risk is OverfittingRisk.HIGH
        # The assessment returns normally - nothing rejects, blocks, or gates.
        assert "reject" not in dir(assessment)
        assert "approved" not in dir(assessment)

    def test_degenerate_zero_trades_low_with_reason(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10], oos_trades=[0, 0, 0])
        assert assessment.overfitting_risk is OverfittingRisk.LOW
        assert any("zero OOS trades" in reason for reason in assessment.reasons)

    def test_degenerate_few_periods_low_with_reason(self) -> None:
        assessment = _assess(2, oos_returns=[0.049, 0.049])
        assert assessment.overfitting_risk is OverfittingRisk.LOW
        assert any("fewer than 3 periods" in reason for reason in assessment.reasons)
        # Flags are still reported even when the risk is capped.
        assert _flag(assessment, "degradation_total_return").triggered

    def test_risk_levels_exactly_v1_members(self) -> None:
        assert [member.value for member in OverfittingRisk] == ["LOW", "MEDIUM", "HIGH"]


class TestAssessmentShape:
    def test_flags_order_fixed(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10])
        assert [flag.name for flag in assessment.flags] == list(OVERFITTING_FLAG_NAMES)

    def test_flags_always_present(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10])
        assert len(assessment.flags) == len(OVERFITTING_FLAG_NAMES)
        assert all(not flag.triggered for flag in assessment.flags)

    def test_assessment_frozen(self) -> None:
        assessment = _assess(3, oos_returns=[0.10, 0.10, 0.10])
        with pytest.raises(FrozenInstanceError):
            assessment.overfitting_risk = OverfittingRisk.HIGH  # type: ignore[misc]

    def test_threshold_constants_fixed_and_exported(self) -> None:
        assert DEGRADATION_THRESHOLD == Decimal("0.5")
        assert LOW_TRADE_COUNT_THRESHOLD == 30
        assert MAX_RETURN_SANITY_BOUND == Decimal("100")
        assert DEPENDENCY_CV_THRESHOLD == Decimal("1.0")
        assert MIN_PERIODS_FOR_ASSESSMENT == 3
        assert isinstance(OVERFITTING_FLAG_POLICY, str)
        assert "No auto-reject" in OVERFITTING_FLAG_POLICY or "no auto-reject" in OVERFITTING_FLAG_POLICY

    def test_assess_rejects_mismatched_period_count(self) -> None:
        periods = _periods(3, oos_returns=[0.10, 0.10, 0.10])
        other = _periods(2, oos_returns=[0.10, 0.10])
        with pytest.raises(WalkForwardError, match="period_count"):
            assess_overfitting(periods=periods, aggregate=aggregate_periods(periods=other))

    def test_assess_rejects_non_tuple(self) -> None:
        periods = _periods(3, oos_returns=[0.10, 0.10, 0.10])
        aggregate = aggregate_periods(periods=periods)
        with pytest.raises(WalkForwardError, match="non-empty tuple"):
            assess_overfitting(periods=list(periods), aggregate=aggregate)  # type: ignore[arg-type]

    def test_reasons_deterministic_order(self) -> None:
        assessment = _assess(
            3,
            oos_returns=[0.049, 0.049, 0.049],
            oos_trades=[3, 4, 3],
            oos_max_drawdown=[Decimal("0.16"), Decimal("0.16"), Decimal("0.16")],
        )
        assert isinstance(assessment.reasons, tuple)
        assert all(isinstance(reason, str) and reason for reason in assessment.reasons)
        # Triggered-flag reasons appear in OVERFITTING_FLAG_NAMES order.
        flag_reasons = [reason for reason in assessment.reasons if reason.startswith("degradation=")]
        assert flag_reasons == sorted(flag_reasons)
