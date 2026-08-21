"""Phase 23 — Full system verification (fail-closed safety chain).

Verifies the three LIVE-readiness safety controls work together and remain
fail-closed: the kill switch (GlobalHaltController), the 17 LIVE safety gates
(LiveSafetyGateEvaluator), and the circuit breaker — all on top of the real
RiskService boundary. LIVE is never enabled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpha_algo_contracts import RiskDecisionResult
from alpha_algo_risk_engine import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    GlobalHaltController,
    LiveSafetyGateEvaluator,
    LiveSafetyGateSnapshot,
)
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.service import RiskService

from risk_test_support import FakeRiskProvider, make_buy_signal, make_snapshot


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
        evaluated_source="full-system-verification",
    )


def test_kill_switch_halts_instantly_and_lifts_cleanly() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)

    # Default: halted → risk service rejects everything.
    svc_halted = RiskService(
        provider=FakeRiskProvider(make_snapshot(global_halt_active=controller.is_halted())),
        circuit_breaker=CircuitBreakerRegistry(),
    )
    outcome = svc_halted.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "GLOBAL_HALT_ACTIVE"

    # Lift the halt (explicit reason + actor) → happy path approves.
    controller.deactivate(reason="full system verification passed", actor="operator")
    svc_clear = RiskService(
        provider=FakeRiskProvider(make_snapshot(global_halt_active=controller.is_halted())),
        circuit_breaker=CircuitBreakerRegistry(),
    )
    outcome = svc_clear.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "APPROVED"
    assert outcome.decision.decision == RiskDecisionResult.APPROVED


def test_safety_gates_green_and_halt_lifted_do_not_enable_live() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW, initial_active=False, initial_reason="")
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    decision = evaluator.evaluate(_all_green(), controller.state)

    # Gates green + halt inactive → the safety-gate layer says LIVE *could* be
    # enabled. But the RiskService still blocks LIVE because live_trading_enabled
    # is false (config-level fail-closed) — LIVE is never actually reached.
    assert decision.can_enable_live is True
    assert decision.reason_code == "LIVE_SAFETY_GATES_PASSED"

    svc = RiskService(
        provider=FakeRiskProvider(make_snapshot(global_halt_active=False, live_trading_enabled=False)),
        circuit_breaker=CircuitBreakerRegistry(),
    )
    live_outcome = svc.evaluate(make_buy_signal(), trading_mode="LIVE")
    assert live_outcome.status == "REJECTED"
    assert live_outcome.decision.reason_code == "LIVE_MODE_BLOCKED"


def test_circuit_breaker_trips_and_resets_end_to_end() -> None:
    state = {"now": FIXED_NOW}
    config = CircuitBreakerConfig(
        failure_threshold=2,
        window=timedelta(seconds=60),
        reset_after=timedelta(seconds=30),
        half_open_probe_limit=1,
    )
    breaker = CircuitBreaker(config=config, clock=lambda: state["now"])

    # Closed → allows.
    assert breaker.allows() is True
    breaker.record_failure()
    breaker.record_failure()  # reaches threshold → OPEN
    assert breaker.allows() is False  # fail-closed while open

    # Advance past reset_after → eligible for HALF_OPEN on next allows().
    state["now"] = FIXED_NOW + timedelta(seconds=31)
    assert breaker.allows() is True  # HALF_OPEN probe
    breaker.record_success()  # probe succeeds → CLOSED
    assert breaker.allows() is True


def test_kill_switch_is_single_authoritative_halt_source() -> None:
    """A single controller drives both the risk boundary and the gate evaluator."""
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    evaluator = LiveSafetyGateEvaluator(clock=lambda: FIXED_NOW)

    decision = evaluator.evaluate(_all_green(), controller.state)
    assert decision.can_enable_live is False
    assert decision.reason_code == "GLOBAL_HALT_ACTIVE"

    controller.deactivate(reason="verified", actor="operator")
    decision = evaluator.evaluate(_all_green(), controller.state)
    assert decision.can_enable_live is True
