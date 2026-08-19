"""RiskService — runtime-connected risk evaluation (Phase 6).

Flow: StrategySignal → circuit-breaker pre-check → risk snapshot → context →
context validation → RiskRuleEngine → bind approval → persist RiskEvent → fan-out
to a (future Phase 7) consumer. LIVE/unknown trading mode is rejected at the
boundary. Duplicate/replayed signals return the prior decision deterministically
without creating a new approval, and an APPROVED decision is fanned out only
after its durable COMMIT (the boundary of truth).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import (
    RiskAssessmentRequest,
    RiskDecision,
    RiskDecisionResult,
    StrategySignal,
)
from alpha_algo_risk_engine.approval import (
    approval_is_usable,
    compute_risk_identity_key,
)
from alpha_algo_risk_engine.circuit_breaker import CircuitBreakerRegistry
from alpha_algo_risk_engine.context import (
    RiskContextBuilder,
    RiskContextUnavailable,
    RiskContextValidator,
    RiskOrderIntent,
)
from alpha_algo_risk_engine.engine import RiskRuleEngine
from alpha_algo_risk_engine.metrics import RiskMetrics
from alpha_algo_risk_engine.repository import (
    OUTCOME_INSERTED,
    RiskEventRepository,
    to_orm_risk_event,
)
from alpha_algo_risk_engine.state import RiskStateProvider, UnavailableRiskStateProvider

logger = logging.getLogger(__name__)

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


@dataclass(frozen=True)
class RiskEvaluationOutcome:
    decision: RiskDecision
    status: str  # APPROVED / REJECTED / DUPLICATE
    persisted: bool = False
    record_id: UUID | None = None
    snapshot_id: UUID | None = None
    prior_decision_id: UUID | None = None


RiskDecisionConsumer = Callable[[RiskDecision], None]


class RiskService:
    def __init__(
        self,
        *,
        provider: RiskStateProvider | None = None,
        repository: RiskEventRepository | None = None,
        engine: RiskRuleEngine | None = None,
        circuit_breaker: CircuitBreakerRegistry | None = None,
        metrics: RiskMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        idempotency_capacity: int = 4096,
    ) -> None:
        self._provider = provider or UnavailableRiskStateProvider()
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._engine = engine or RiskRuleEngine(clock=self._clock)
        self._builder = RiskContextBuilder(clock=self._clock)
        self._validator = RiskContextValidator()
        self._breaker = circuit_breaker or CircuitBreakerRegistry(clock=self._clock)
        self._metrics = metrics or RiskMetrics()
        self._consumers: list[RiskDecisionConsumer] = []
        self._decisions: OrderedDict[str, RiskDecision] = OrderedDict()
        self._retries: OrderedDict[str, int] = OrderedDict()
        self._capacity = idempotency_capacity
        self._lock = threading.RLock()

    @property
    def metrics(self) -> RiskMetrics:
        return self._metrics

    def add_consumer(self, consumer: RiskDecisionConsumer) -> None:
        self._consumers.append(consumer)

    def evaluate(
        self,
        signal: StrategySignal,
        *,
        intent: RiskOrderIntent | None = None,
        trading_mode: str = "PAPER",
    ) -> RiskEvaluationOutcome:
        start = perf_counter()
        self._metrics.inc("evaluations")

        mode = trading_mode.upper()
        now = self._clock()
        identity_key = compute_risk_identity_key(signal, intent, mode)
        request = RiskAssessmentRequest(signal=signal, requested_at=now)

        with self._lock:
            return self._evaluate_locked(
                request, signal, intent, mode, identity_key, now, start
            )

    # --- internal -----------------------------------------------------------

    def _evaluate_locked(
        self,
        request: RiskAssessmentRequest,
        signal: StrategySignal,
        intent: RiskOrderIntent | None,
        mode: str,
        identity_key: str,
        now: datetime,
        start: float,
    ) -> RiskEvaluationOutcome:
        # 1. Trading-mode gate (fail-closed boundary: LIVE/unknown rejected).
        if mode not in _ALLOWED_MODES:
            decision = self._make_reject(
                request, "core.live-mode-gate", "LIVE_MODE_BLOCKED",
                f"trading mode not allowed: {mode}", now,
            )
            self._metrics.inc("rejections")
            self._metrics.inc_rule("core.live-mode-gate")
            return self._finish_reject(
                decision, intent, mode, None, identity_key, start
            )

        # 2. Duplicate / replay → prior decision (no new approval). Re-validate
        #    a prior APPROVED so a stale/expired/unbound approval is never
        #    returned on replay.
        prior = self._decisions.get(identity_key)
        if prior is not None:
            self._metrics.inc("duplicates")
            if (
                prior.decision == RiskDecisionResult.APPROVED
                and not approval_is_usable(prior, now, binding_hash=identity_key)
            ):
                decision = self._make_reject(
                    request, "core.duplicate-order-protection", "PRIOR_APPROVAL_INVALID",
                    "prior approval expired or unbound on replay", now,
                )
                self._metrics.inc("rejections")
                self._metrics.inc_rule("core.duplicate-order-protection")
                return self._finish_reject(
                    decision, intent, mode, None, identity_key, start
                )
            self._metrics.record_latency(perf_counter() - start)
            return RiskEvaluationOutcome(
                decision=prior, status="DUPLICATE", prior_decision_id=prior.decision_id
            )

        # 3. Circuit-breaker pre-check (fail-closed).
        scopes = [
            "global",
            f"strategy:{signal.strategy_id}",
            f"instrument:{signal.instrument_id}",
        ]
        for scope in scopes:
            if not self._breaker.allows(scope, now):
                self._metrics.inc("circuit_breaker_trips")
                decision = self._make_reject(
                    request, "core.circuit-breaker", "CIRCUIT_BREAKER_OPEN",
                    f"circuit breaker open: {scope}", now,
                )
                self._metrics.inc("rejections")
                self._metrics.inc_rule("core.circuit-breaker")
                return self._finish_reject(
                    decision, intent, mode, None, identity_key, start
                )

        # 4. Snapshot → context (fail-closed on unavailable/stale/mismatched state).
        try:
            snapshot = self._provider.get_snapshot(
                account_id=intent.account_id if intent is not None else None,
                instrument_id=signal.instrument_id,
                strategy_id=signal.strategy_id,
            )
            retry_count = self._retries.get(identity_key, 0)
            context = self._builder.build(
                signal, intent, snapshot, trading_mode=mode, retry_count=retry_count
            )
        except RiskContextUnavailable as exc:
            self._metrics.inc("context_unavailable")
            decision = self._make_reject(
                request, "core.risk-context", "RISK_STATE_UNAVAILABLE", str(exc), now
            )
            self._metrics.inc("rejections")
            self._metrics.inc_rule("core.risk-context")
            return self._finish_reject(
                decision, intent, mode, None, identity_key, start
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on any context fault
            self._metrics.inc("errors")
            decision = self._make_reject(
                request, "core.risk-context", "RISK_CONTEXT_ERROR",
                f"context construction failed: {type(exc).__name__}", now,
            )
            self._metrics.inc("rejections")
            self._metrics.inc_rule("core.risk-context")
            return self._finish_reject(
                decision, intent, mode, None, identity_key, start
            )

        # 5. Context validation (cross-field consistency).
        problems = self._validator.validate(context)
        if problems:
            decision = self._make_reject(
                request, "core.risk-context", "RISK_CONTEXT_INVALID", "; ".join(problems), now
            )
            self._metrics.inc("rejections")
            self._metrics.inc_rule("core.risk-context")
            return self._finish_reject(
                decision, intent, mode, None, identity_key, start
            )

        # 6. Run the rule engine.
        decision = self._engine.evaluate(request, context)

        # 7. Bind approval identity (binding = identity key) + snapshot identity.
        if decision.decision == RiskDecisionResult.APPROVED:
            decision = decision.model_copy(
                update={"binding_hash": identity_key, "snapshot_id": snapshot.snapshot_id}
            )

        # 8. Circuit-breaker outcome recording.
        if decision.decision == RiskDecisionResult.APPROVED:
            for scope in scopes:
                self._breaker.record_success(scope, now)
            self._metrics.inc("approvals")
            status = "APPROVED"
        else:
            for scope in scopes:
                self._breaker.record_failure(scope, now)
            self._metrics.inc("rejections")
            self._metrics.inc_rule(decision.rule_id)
            if decision.rule_id == "core.global-halt":
                self._metrics.inc("global_halt_rejections")
            if decision.reason_code == "STALE_MARKET_DATA":
                self._metrics.inc("stale_data_rejections")
            status = "REJECTED"

        # 9. Retry accounting (bounded alongside the dedup map).
        self._retries[identity_key] = self._retries.get(identity_key, 0) + 1
        self._retries.move_to_end(identity_key)

        # 10. Persist (durable commit) then record + fan-out. APPROVED is fanned
        #     out only after a durable commit; a failed commit is fail-closed
        #     (not recorded, not fanned out) so a replay re-attempts persistence.
        snapshot_id = snapshot.snapshot_id
        persisted, record_id = self._persist(decision, intent, mode, snapshot_id, identity_key)
        has_durable_boundary = self._repository is not None

        if decision.decision == RiskDecisionResult.APPROVED:
            # Fan out only when the approval is durably committed. When no
            # repository is wired (repository-less simulation), persistence is
            # not applicable, so the in-memory record + fan-out proceed.
            if persisted or not has_durable_boundary:
                self._record_seen(identity_key, decision)
                self._fan_out(decision)
        else:
            self._record_seen(identity_key, decision)  # deterministic replay for rejections

        self._metrics.record_latency(perf_counter() - start)
        return RiskEvaluationOutcome(
            decision=decision,
            status=status,
            persisted=persisted,
            record_id=record_id,
            snapshot_id=snapshot_id,
        )

    def _make_reject(
        self,
        request: RiskAssessmentRequest,
        rule_id: str,
        reason_code: str,
        reason: str,
        now: datetime,
    ) -> RiskDecision:
        return RiskDecision(
            request_id=request.request_id,
            signal_id=request.signal.signal_id,
            strategy_id=request.signal.strategy_id,
            instrument_id=request.signal.instrument_id,
            decision=RiskDecisionResult.REJECTED,
            reason_code=reason_code,
            reason=reason,
            rule_id=rule_id,
            evaluated_at=now,
        )

    def _finish_reject(
        self,
        decision: RiskDecision,
        intent: RiskOrderIntent | None,
        mode: str,
        snapshot_id: UUID | None,
        identity_key: str,
        start: float,
    ) -> RiskEvaluationOutcome:
        self._record_seen(identity_key, decision)
        persisted, record_id = self._persist(decision, intent, mode, snapshot_id, identity_key)
        self._metrics.record_latency(perf_counter() - start)
        return RiskEvaluationOutcome(
            decision=decision,
            status="REJECTED",
            persisted=persisted,
            record_id=record_id,
            snapshot_id=snapshot_id,
        )

    def _persist(
        self,
        decision: RiskDecision,
        intent: RiskOrderIntent | None,
        mode: str,
        snapshot_id: UUID | None,
        identity_key: str,
    ) -> tuple[bool, UUID | None]:
        if self._repository is None:
            return False, None
        event = to_orm_risk_event(
            decision,
            account_id=intent.account_id if intent is not None else None,
            trading_mode=mode,
            snapshot_id=snapshot_id,
            identity_key=identity_key,
        )
        try:
            outcome, record_id = self._repository.persist(event)
            return outcome == OUTCOME_INSERTED, record_id
        except Exception as exc:  # noqa: BLE001 - DB failure → no false committed
            self._metrics.inc("persistence_failures")
            logger.warning("risk event persistence failed: %s", exc)
            return False, None

    def _record_seen(self, identity_key: str, decision: RiskDecision) -> None:
        self._decisions[identity_key] = decision
        self._decisions.move_to_end(identity_key)
        while len(self._decisions) > self._capacity:
            evicted, _ = self._decisions.popitem(last=False)
            self._retries.pop(evicted, None)

    def _fan_out(self, decision: RiskDecision) -> None:
        for consumer in self._consumers:
            try:
                consumer(decision)
            except Exception as exc:  # noqa: BLE001 - isolate consumer faults
                logger.warning("risk decision consumer failed: %s", exc)
