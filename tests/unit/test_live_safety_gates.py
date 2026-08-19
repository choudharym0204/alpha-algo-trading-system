from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_algo_risk_engine import (
    GlobalHaltState,
    LiveSafetyGate,
    LiveSafetyGateEvaluator,
    LiveSafetyGateSnapshot,
)


FIXED_NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def _all_green_snapshot() -> LiveSafetyGateSnapshot:
    return LiveSafetyGateSnapshot(
        market_data_stable=True,
        broker_connection_stable=True,
        strategy_tests_passing=True,
        risk_tests_passing=True,
        execution_tests_passing=True,
        reconciliation_working=True,
        paper_trading_verified=True,
        emergency_stop_verified=True,
        circuit_breakers_verified=True,
        position_calculations_verified=True,
        pnl_verified=True,
        duplicate_order_protection_verified=True,
        broker_failure_handling_verified=True,
        database_persistence_verified=True,
        audit_logging_verified=True,
        monitoring_verified=True,
        security_checks_passed=True,
        evaluated_source="unit-test",
    )


def test_live_safety_gates_default_to_disabled() -> None:
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    decision = evaluator.evaluate(LiveSafetyGateSnapshot())

    assert decision.can_enable_live is False
    assert decision.reason_code == "GLOBAL_HALT_ACTIVE"
    assert decision.global_halt_active is True
    assert len(decision.failed_gates) == len(LiveSafetyGate)


def test_live_safety_gates_pass_only_when_all_gates_green_and_halt_inactive() -> None:
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    decision = evaluator.evaluate(
        _all_green_snapshot(),
        GlobalHaltState(active=False, reason="", updated_at=FIXED_NOW, updated_by="operator"),
    )

    assert decision.can_enable_live is True
    assert decision.reason_code == "LIVE_SAFETY_GATES_PASSED"
    assert decision.failed_gates == ()
    assert decision.global_halt_active is False


def test_global_halt_blocks_live_even_when_all_gates_pass() -> None:
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    decision = evaluator.evaluate(
        _all_green_snapshot(),
        GlobalHaltState(
            active=True,
            reason="manual emergency stop",
            updated_at=FIXED_NOW,
            updated_by="operator",
        ),
    )

    assert decision.can_enable_live is False
    assert decision.reason_code == "GLOBAL_HALT_ACTIVE"
    assert decision.reason == "manual emergency stop"


def test_any_failed_gate_blocks_live() -> None:
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)
    snapshot = LiveSafetyGateSnapshot(
        **{**_all_green_snapshot().__dict__, "monitoring_verified": False}
    )

    decision = evaluator.evaluate(
        snapshot,
        GlobalHaltState(active=False, reason="", updated_at=FIXED_NOW, updated_by="operator"),
    )

    assert decision.can_enable_live is False
    assert decision.reason_code == "LIVE_SAFETY_GATES_FAILED"
    assert decision.failed_gates == (LiveSafetyGate.MONITORING_VERIFIED,)


def test_global_halt_state_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GlobalHaltState(active=True, reason="halt", updated_at=datetime(2026, 1, 1))


def test_active_global_halt_requires_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        GlobalHaltState(active=True, reason=" ", updated_at=FIXED_NOW)


def test_live_gate_evaluator_exposes_no_broker_order_submission_methods() -> None:
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    forbidden_names = {
        "broker",
        "broker_credentials",
        "credentials",
        "place_order",
        "submit_order",
        "send_order",
        "execute_order",
    }

    assert forbidden_names.isdisjoint(dir(evaluator))
