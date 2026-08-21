"""Phase 24 — LiveReleaseController (controlled LIVE release progression) tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_algo_risk_engine import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    GlobalHaltController,
    LiveReleaseController,
    LiveReleaseDecision,
    LiveReleaseStage,
    LiveSafetyGateEvaluator,
    LiveSafetyGateSnapshot,
)


FIXED_NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def _all_green() -> LiveSafetyGateSnapshot:
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
        evaluated_source="test",
    )


def _controller(*, halt_active: bool = True, breakers: CircuitBreakerRegistry | None = None) -> LiveReleaseController:
    return LiveReleaseController(
        halt_controller=GlobalHaltController(
            clock=lambda: FIXED_NOW,
            initial_active=halt_active,
            initial_reason="default safety halt" if halt_active else "",
        ),
        gates=LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW),
        circuit_breakers=breakers or CircuitBreakerRegistry(clock=lambda: FIXED_NOW),
        clock=lambda: FIXED_NOW,
    )


def test_starts_disabled() -> None:
    assert _controller().stage is LiveReleaseStage.DISABLED


def test_advance_requires_actor_and_reason() -> None:
    controller = _controller(halt_active=False)
    with pytest.raises(ValueError, match="reason"):
        controller.advance_to_shadow(actor="op", reason="  ", snapshot=_all_green())
    with pytest.raises(ValueError, match="actor"):
        controller.advance_to_shadow(actor=" ", reason="go", snapshot=_all_green())


def test_advance_to_shadow_green() -> None:
    controller = _controller(halt_active=False)
    decision = controller.advance_to_shadow(actor="op", reason="shadow start", snapshot=_all_green())
    assert decision.approved is True
    assert decision.reason_code == "RELEASE_APPROVED"
    assert decision.stage is LiveReleaseStage.SHADOW
    assert controller.stage is LiveReleaseStage.SHADOW


def test_advance_to_shadow_blocked_by_failed_gate() -> None:
    controller = _controller(halt_active=False)
    snapshot = _all_green()
    snapshot = LiveSafetyGateSnapshot(**{**snapshot.__dict__, "pnl_verified": False})
    decision = controller.advance_to_shadow(actor="op", reason="shadow", snapshot=snapshot)
    assert decision.approved is False
    assert decision.reason_code == "LIVE_SAFETY_GATES_FAILED"
    assert "pnl_verified" in {g.value for g in decision.failed_gates}
    assert controller.stage is LiveReleaseStage.DISABLED


def test_advance_to_shadow_blocked_by_halt() -> None:
    controller = _controller(halt_active=True)  # still halted
    decision = controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    assert decision.approved is False
    assert decision.reason_code == "GLOBAL_HALT_ACTIVE"
    assert controller.stage is LiveReleaseStage.DISABLED


def test_advance_to_full_requires_shadow_first() -> None:
    controller = _controller(halt_active=False)
    decision = controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    assert decision.approved is False
    assert decision.reason_code == "NOT_IN_SHADOW"
    assert controller.stage is LiveReleaseStage.DISABLED


def test_advance_to_full_green() -> None:
    controller = _controller(halt_active=False)
    controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    decision = controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    assert decision.approved is True
    assert decision.reason_code == "RELEASE_APPROVED"
    assert controller.stage is LiveReleaseStage.FULL


def test_advance_to_full_blocked_by_open_breaker() -> None:
    breakers = CircuitBreakerRegistry(CircuitBreakerConfig(failure_threshold=1), clock=lambda: FIXED_NOW)
    controller = _controller(halt_active=False, breakers=breakers)
    controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    breakers.record_failure("global")  # opens the global breaker
    decision = controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    assert decision.approved is False
    assert decision.reason_code == "CIRCUIT_BREAKER_OPEN"
    assert decision.circuit_breaker_open is True
    assert controller.stage is LiveReleaseStage.SHADOW


def test_disable_pulls_back_to_disabled() -> None:
    controller = _controller(halt_active=False)
    controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    assert controller.stage is LiveReleaseStage.FULL
    controller.disable(actor="op", reason="incident")
    assert controller.stage is LiveReleaseStage.DISABLED


def test_advance_idempotent_guards() -> None:
    controller = _controller(halt_active=False)
    controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    again = controller.advance_to_shadow(actor="op", reason="again", snapshot=_all_green())
    assert again.approved is False
    assert again.reason_code == "ALREADY_SHADOW"

    controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    full_again = controller.advance_to_full(actor="op", reason="again", snapshot=_all_green())
    assert full_again.approved is False
    assert full_again.reason_code == "ALREADY_FULL"


def test_can_submit_live_is_fail_closed() -> None:
    controller = _controller(halt_active=False)

    # Not FULL → never submittable.
    assert controller.can_submit_live(live_trading_enabled=True) is False

    controller.advance_to_shadow(actor="op", reason="shadow", snapshot=_all_green())
    assert controller.can_submit_live(live_trading_enabled=True) is False  # SHADOW only

    controller.advance_to_full(actor="op", reason="full", snapshot=_all_green())
    # FULL but config still disables LIVE.
    assert controller.can_submit_live(live_trading_enabled=False) is False
    # FULL + config on → advisory True.
    assert controller.can_submit_live(live_trading_enabled=True) is True

    # Re-trigger the kill switch → fail-closed again.
    controller._halt.activate(reason="emergency", actor="op")
    assert controller.can_submit_live(live_trading_enabled=True) is False


def test_decision_invariant_rejects_approved_with_failed_gates() -> None:
    with pytest.raises(ValueError, match="failed gates"):
        LiveReleaseDecision(
            stage=LiveReleaseStage.SHADOW,
            approved=True,
            reason_code="RELEASE_APPROVED",
            reason="bad",
            evaluated_at=FIXED_NOW,
            failed_gates=("pnl_verified",),  # type: ignore[arg-type]
            global_halt_active=False,
            circuit_breaker_open=False,
        )
