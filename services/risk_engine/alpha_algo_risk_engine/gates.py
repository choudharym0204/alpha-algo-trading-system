from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable

from alpha_algo_risk_engine.circuit_breaker import CircuitBreakerRegistry


class LiveSafetyGate(StrEnum):
    MARKET_DATA_STABLE = "market_data_stable"
    BROKER_CONNECTION_STABLE = "broker_connection_stable"
    STRATEGY_TESTS_PASSING = "strategy_tests_passing"
    RISK_TESTS_PASSING = "risk_tests_passing"
    EXECUTION_TESTS_PASSING = "execution_tests_passing"
    RECONCILIATION_WORKING = "reconciliation_working"
    PAPER_TRADING_VERIFIED = "paper_trading_verified"
    EMERGENCY_STOP_VERIFIED = "emergency_stop_verified"
    CIRCUIT_BREAKERS_VERIFIED = "circuit_breakers_verified"
    POSITION_CALCULATIONS_VERIFIED = "position_calculations_verified"
    PNL_VERIFIED = "pnl_verified"
    DUPLICATE_ORDER_PROTECTION_VERIFIED = "duplicate_order_protection_verified"
    BROKER_FAILURE_HANDLING_VERIFIED = "broker_failure_handling_verified"
    DATABASE_PERSISTENCE_VERIFIED = "database_persistence_verified"
    AUDIT_LOGGING_VERIFIED = "audit_logging_verified"
    MONITORING_VERIFIED = "monitoring_verified"
    SECURITY_CHECKS_PASSED = "security_checks_passed"


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


@dataclass(frozen=True)
class GlobalHaltState:
    active: bool = True
    reason: str = "default safety halt"
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_by: str = "system"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.updated_at):
            raise ValueError("updated_at must be timezone-aware")
        if self.active and not self.reason.strip():
            raise ValueError("active global halt requires reason")
        if not self.updated_by.strip():
            raise ValueError("updated_by is required")


@dataclass(frozen=True)
class LiveSafetyGateSnapshot:
    market_data_stable: bool = False
    broker_connection_stable: bool = False
    strategy_tests_passing: bool = False
    risk_tests_passing: bool = False
    execution_tests_passing: bool = False
    reconciliation_working: bool = False
    paper_trading_verified: bool = False
    emergency_stop_verified: bool = False
    circuit_breakers_verified: bool = False
    position_calculations_verified: bool = False
    pnl_verified: bool = False
    duplicate_order_protection_verified: bool = False
    broker_failure_handling_verified: bool = False
    database_persistence_verified: bool = False
    audit_logging_verified: bool = False
    monitoring_verified: bool = False
    security_checks_passed: bool = False
    evaluated_source: str = "manual"
    metadata: dict[str, object] = field(default_factory=dict)

    def failed_gates(self) -> tuple[LiveSafetyGate, ...]:
        return tuple(gate for gate in LiveSafetyGate if not getattr(self, gate.value))

    def all_gates_passed(self) -> bool:
        return not self.failed_gates()


@dataclass(frozen=True)
class LiveSafetyGateDecision:
    can_enable_live: bool
    reason_code: str
    reason: str
    evaluated_at: datetime
    failed_gates: tuple[LiveSafetyGate, ...] = ()
    global_halt_active: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.evaluated_at):
            raise ValueError("evaluated_at must be timezone-aware")
        if self.can_enable_live and (self.failed_gates or self.global_halt_active):
            raise ValueError("LIVE cannot be enabled with failed gates or active global halt")


class LiveSafetyGateEvaluator:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def evaluate(
        self,
        snapshot: LiveSafetyGateSnapshot,
        halt_state: GlobalHaltState | None = None,
    ) -> LiveSafetyGateDecision:
        evaluated_at = self._clock()
        if not _is_timezone_aware(evaluated_at):
            raise ValueError("clock must return a timezone-aware datetime")

        halt = halt_state or GlobalHaltState()
        if halt.active:
            return LiveSafetyGateDecision(
                can_enable_live=False,
                reason_code="GLOBAL_HALT_ACTIVE",
                reason=halt.reason,
                evaluated_at=evaluated_at,
                failed_gates=snapshot.failed_gates(),
                global_halt_active=True,
                metadata={"halt_updated_at": halt.updated_at, "halt_updated_by": halt.updated_by},
            )

        failed_gates = snapshot.failed_gates()
        if failed_gates:
            return LiveSafetyGateDecision(
                can_enable_live=False,
                reason_code="LIVE_SAFETY_GATES_FAILED",
                reason="one or more LIVE safety gates are incomplete",
                evaluated_at=evaluated_at,
                failed_gates=failed_gates,
                global_halt_active=False,
                metadata={"evaluated_source": snapshot.evaluated_source, **snapshot.metadata},
            )

        return LiveSafetyGateDecision(
            can_enable_live=True,
            reason_code="LIVE_SAFETY_GATES_PASSED",
            reason="all LIVE safety gates passed and global halt is inactive",
            evaluated_at=evaluated_at,
            failed_gates=(),
            global_halt_active=False,
            metadata={"evaluated_source": snapshot.evaluated_source, **snapshot.metadata},
        )


class GlobalHaltController:
    """Kill switch — authoritative, fail-closed global trading halt (Phase 23).

    Starts **ACTIVE** (halted). ``activate`` halts instantly with an auditable
    reason and actor; ``deactivate`` lifts the halt only with an explicit reason
    and actor (never silently). State is immutable and transitions are atomic, so
    a concurrent risk/execution check always observes a consistent halt state.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        initial_active: bool = True,
        initial_reason: str = "default safety halt",
    ) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._lock = threading.Lock()
        self._state = GlobalHaltState(
            active=initial_active,
            reason=initial_reason if initial_active else "",
            updated_at=self._clock(),
            updated_by="system",
        )

    @property
    def state(self) -> GlobalHaltState:
        with self._lock:
            return self._state

    def is_halted(self) -> bool:
        """True when trading is halted (fail-closed default)."""
        return self.state.active

    def activate(self, *, reason: str, actor: str) -> GlobalHaltState:
        """Trigger the kill switch: halt all trading instantly."""
        self._require_reason_and_actor(reason, actor)
        with self._lock:
            self._state = GlobalHaltState(
                active=True,
                reason=reason,
                updated_at=self._clock(),
                updated_by=actor,
            )
            return self._state

    def deactivate(self, *, reason: str, actor: str) -> GlobalHaltState:
        """Lift the halt — requires an explicit, audited reason and actor."""
        self._require_reason_and_actor(reason, actor)
        with self._lock:
            self._state = GlobalHaltState(
                active=False,
                reason="",
                updated_at=self._clock(),
                updated_by=actor,
                metadata={"deactivate_reason": reason},
            )
            return self._state

    @staticmethod
    def _require_reason_and_actor(reason: str, actor: str) -> None:
        if not reason.strip():
            raise ValueError("reason is required")
        if not actor.strip():
            raise ValueError("actor is required")


class LiveReleaseStage(StrEnum):
    """Controlled LIVE release progression stages (Phase 24)."""

    DISABLED = "DISABLED"  # no live readiness; nothing can submit
    SHADOW = "SHADOW"      # real connectivity + data, but no real orders
    FULL = "FULL"          # real orders permitted *only* if every gate still holds


@dataclass(frozen=True)
class LiveReleaseDecision:
    stage: LiveReleaseStage
    approved: bool
    reason_code: str
    reason: str
    evaluated_at: datetime
    failed_gates: tuple[LiveSafetyGate, ...] = ()
    global_halt_active: bool = True
    circuit_breaker_open: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.evaluated_at):
            raise ValueError("evaluated_at must be timezone-aware")
        if self.approved and (self.failed_gates or self.global_halt_active or self.circuit_breaker_open):
            raise ValueError(
                "release cannot be approved with failed gates, an active global halt, or an open circuit breaker"
            )


class LiveReleaseController:
    """Controlled LIVE release progression — DISABLED → SHADOW → FULL (Phase 24).

    A fail-closed operational readiness controller. The release stage advances
    only through explicit, audited transitions that re-evaluate the 17 LIVE
    safety gates, the global halt (kill switch), and the circuit breaker:

        DISABLED --advance_to_shadow--> SHADOW --advance_to_full--> FULL

    ``disable`` pulls back to DISABLED at any time. This controller is
    **advisory readiness only**: it never enables real order submission, which
    remains behind the existing LIVE fail-closed guards (``LiveModeRule``,
    ``GlobalHaltRule``, broker ``_guard_live``, ``LIVE_TRADING_ENABLED=false``).
    """

    def __init__(
        self,
        *,
        halt_controller: GlobalHaltController | None = None,
        gates: LiveSafetyGateEvaluator | None = None,
        circuit_breakers: CircuitBreakerRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._halt = halt_controller or GlobalHaltController(clock=self._clock)
        self._gates = gates or LiveSafetyGateEvaluator(clock=self._clock)
        self._breakers = circuit_breakers or CircuitBreakerRegistry(clock=self._clock)
        self._lock = threading.Lock()
        self._stage = LiveReleaseStage.DISABLED

    @property
    def stage(self) -> LiveReleaseStage:
        with self._lock:
            return self._stage

    def advance_to_shadow(
        self,
        *,
        actor: str,
        reason: str,
        snapshot: LiveSafetyGateSnapshot,
    ) -> LiveReleaseDecision:
        self._require_actor_reason(actor, reason)
        with self._lock:
            if self._stage is LiveReleaseStage.SHADOW:
                return self._current(LiveReleaseStage.SHADOW, "ALREADY_SHADOW", "already in SHADOW stage", actor)
            if self._stage is LiveReleaseStage.FULL:
                return self._current(LiveReleaseStage.FULL, "ALREADY_FULL", "already in FULL stage; disable() to pull back", actor)
        decision = self._evaluate(LiveReleaseStage.SHADOW, snapshot, actor)
        if decision.approved:
            with self._lock:
                self._stage = LiveReleaseStage.SHADOW
        return decision

    def advance_to_full(
        self,
        *,
        actor: str,
        reason: str,
        snapshot: LiveSafetyGateSnapshot,
    ) -> LiveReleaseDecision:
        self._require_actor_reason(actor, reason)
        with self._lock:
            if self._stage is LiveReleaseStage.DISABLED:
                return self._current(LiveReleaseStage.DISABLED, "NOT_IN_SHADOW", "must advance to SHADOW before FULL", actor)
            if self._stage is LiveReleaseStage.FULL:
                return self._current(LiveReleaseStage.FULL, "ALREADY_FULL", "already in FULL stage", actor)
        decision = self._evaluate(LiveReleaseStage.FULL, snapshot, actor)
        if decision.approved:
            with self._lock:
                self._stage = LiveReleaseStage.FULL
        return decision

    def disable(self, *, actor: str, reason: str) -> None:
        """Pull back to DISABLED (always allowed — fail-closed)."""
        self._require_actor_reason(actor, reason)
        with self._lock:
            self._stage = LiveReleaseStage.DISABLED

    def can_submit_live(self, *, live_trading_enabled: bool) -> bool:
        """Advisory readiness signal (default False). Never enables submission itself."""
        if self.stage is not LiveReleaseStage.FULL:
            return False
        return bool(live_trading_enabled) and not self._halt.is_halted() and not self._breaker_open()

    def _breaker_open(self) -> bool:
        return not self._breakers.allows("global")

    def _current(
        self,
        stage: LiveReleaseStage,
        reason_code: str,
        reason: str,
        actor: str,
    ) -> LiveReleaseDecision:
        return LiveReleaseDecision(
            stage=stage,
            approved=False,
            reason_code=reason_code,
            reason=reason,
            evaluated_at=self._clock(),
            failed_gates=(),
            global_halt_active=self._halt.is_halted(),
            circuit_breaker_open=self._breaker_open(),
            metadata={"actor": actor},
        )

    def _evaluate(
        self,
        target: LiveReleaseStage,
        snapshot: LiveSafetyGateSnapshot,
        actor: str,
    ) -> LiveReleaseDecision:
        evaluated_at = self._clock()
        halt = self._halt.state
        failed = snapshot.failed_gates()
        breaker_open = self._breaker_open()
        if halt.active:
            return LiveReleaseDecision(
                target,
                False,
                "GLOBAL_HALT_ACTIVE",
                halt.reason,
                evaluated_at,
                failed,
                True,
                breaker_open,
                metadata={"actor": actor},
            )
        if failed:
            return LiveReleaseDecision(
                target,
                False,
                "LIVE_SAFETY_GATES_FAILED",
                "one or more LIVE safety gates are incomplete",
                evaluated_at,
                failed,
                False,
                breaker_open,
                metadata={"actor": actor, "evaluated_source": snapshot.evaluated_source},
            )
        if breaker_open:
            return LiveReleaseDecision(
                target,
                False,
                "CIRCUIT_BREAKER_OPEN",
                "circuit breaker is open",
                evaluated_at,
                (),
                False,
                True,
                metadata={"actor": actor},
            )
        return LiveReleaseDecision(
            target,
            True,
            "RELEASE_APPROVED",
            f"progression to {target.value} approved",
            evaluated_at,
            (),
            False,
            False,
            metadata={"actor": actor, "evaluated_source": snapshot.evaluated_source},
        )

    @staticmethod
    def _require_actor_reason(actor: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("reason is required")
        if not actor.strip():
            raise ValueError("actor is required")
