"""Trading Orchestrator (Phase 7) — the coordination layer between the Phase-5
Signal Engine, the Phase-6 Risk Engine, and the future Phase-8 OMS.

It owns *coordination only*: it verifies signal acceptance, resolves the order
intent, drives risk evaluation, re-validates the approval binding/expiry, and
persists + hands off a durable, OMS-ready ``TradingIntent``. It does NOT implement
signal validation, risk rules, approval logic, OMS, or broker dispatch. LIVE and
unknown trading modes are blocked (fail closed). The pipeline ends at the OMS port
— never at a broker.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Callable
from uuid import UUID, uuid4

from alpha_algo_contracts import (
    RiskDecision,
    RiskDecisionResult,
    SignalAction,
    StrategySignal,
)
from alpha_algo_risk_engine.approval import approval_is_usable, compute_risk_identity_key
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.service import RiskService
from alpha_algo_signal_engine.identity import compute_signal_identity_key, run_id_from
from alpha_algo_signal_engine.service import SignalRecord
from alpha_algo_signal_engine.state import SignalState
from alpha_algo_trading_engine.identity import compute_orchestration_identity_key
from alpha_algo_trading_engine.intent import (
    OrderIntentResolver,
    TradingIntent,
    UnavailableOrderIntentResolver,
)
from alpha_algo_trading_engine.metrics import OrchestrationMetrics
from alpha_algo_trading_engine.oms_port import NoOpOmsPort, OmsPort
from alpha_algo_trading_engine.repository import (
    OUTCOME_DUPLICATE,
    OUTCOME_INSERTED,
    TradingIntentRepository,
    to_orm_rejection,
    to_orm_trading_intent,
)
from alpha_algo_trading_engine.state import OrchestrationState, OrchestrationStateMachine

logger = logging.getLogger(__name__)

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})

# Actions that produce a tradable intent. HOLD and anything unknown are excluded.
_TRADABLE_ACTIONS = frozenset({SignalAction.BUY, SignalAction.SELL, SignalAction.EXIT})


@dataclass(frozen=True)
class OrchestrationResult:
    state: OrchestrationState
    intent: TradingIntent | None = None
    risk_decision: RiskDecision | None = None
    persisted: bool = False
    record_id: UUID | None = None
    handoff_delivered: bool = False
    reason_code: str | None = None
    reason: str = ""


class TradingOrchestrator:
    def __init__(
        self,
        *,
        risk_service: RiskService,
        intent_resolver: OrderIntentResolver | None = None,
        oms_port: OmsPort | None = None,
        repository: TradingIntentRepository | None = None,
        metrics: OrchestrationMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        idempotency_capacity: int = 4096,
    ) -> None:
        self._risk = risk_service
        self._intent_resolver = intent_resolver or UnavailableOrderIntentResolver()
        self._oms_port = oms_port or NoOpOmsPort()
        self._repository = repository
        self._metrics = metrics or OrchestrationMetrics()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._capacity = idempotency_capacity
        self._handed_off: OrderedDict[str, TradingIntent] = OrderedDict()
        self._lock = threading.RLock()

    @property
    def metrics(self) -> OrchestrationMetrics:
        return self._metrics

    def process_signal(
        self,
        record: SignalRecord,
        *,
        trading_mode: str = "PAPER",
        intent: RiskOrderIntent | None = None,
    ) -> OrchestrationResult:
        start = perf_counter()
        self._metrics.inc("signals_received")
        machine = OrchestrationStateMachine()
        now = self._clock()
        mode = trading_mode.upper()
        signal = record.signal

        # 1. Trading-mode gate (fail closed; LIVE/unknown blocked).
        if mode not in _ALLOWED_MODES:
            return self._reject(
                signal, intent, mode, machine, "LIVE_MODE_BLOCKED",
                f"trading mode not allowed: {mode}", start, persist=False,
            )

        # 2. Signal acceptance: only durably-PERSISTED Phase-5 signals proceed.
        if record.state != SignalState.PERSISTED:
            return self._reject(
                signal, intent, mode, machine, "SIGNAL_NOT_ACCEPTED",
                f"signal not accepted (state={record.state.value})", start, persist=False,
            )

        # 3. Signal identity: the record's identity must match the signal.
        if record.identity_key != compute_signal_identity_key(signal):
            return self._reject(
                signal, intent, mode, machine, "SIGNAL_IDENTITY_MISMATCH",
                "signal record identity does not match the signal", start, persist=False,
            )

        machine.transition(OrchestrationState.VALIDATED)

        # 4. Action validation: HOLD/unknown must never create a trading intent.
        if signal.action not in _TRADABLE_ACTIONS:
            return self._reject(
                signal, intent, mode, machine, "ACTION_NOT_TRADABLE",
                f"action {signal.action.value} does not create a trading intent", start, persist=False,
            )

        # 5. Resolve the order intent (quantity/account/order type). Never invent.
        intent = intent or self._intent_resolver.resolve(signal, mode)
        if intent is None or intent.quantity is None or intent.quantity <= Decimal("0"):
            return self._reject(
                signal, intent, mode, machine, "INTENT_UNAVAILABLE",
                "no valid order quantity resolved", start, persist=False,
            )

        # 6. Risk evaluation (Phase-6 guarantees preserved).
        self._metrics.inc("risk_calls")
        outcome = self._risk.evaluate(signal, intent=intent, trading_mode=mode)
        machine.transition(OrchestrationState.RISK_EVALUATED)
        decision = outcome.decision

        if decision.decision == RiskDecisionResult.REJECTED:
            self._metrics.inc("risk_rejections")
            return self._reject(
                signal, intent, mode, machine, decision.reason_code, decision.reason,
                start, persist=True, decision=decision,
            )

        # 7. Approval validation (expiry + binding). Never substitute an approval.
        self._metrics.inc("risk_approvals")
        binding = compute_risk_identity_key(signal, intent, mode)
        if not approval_is_usable(decision, now, binding_hash=binding):
            return self._reject(
                signal, intent, mode, machine, "PRIOR_APPROVAL_INVALID",
                "approval expired or unbound", start, persist=True, decision=decision,
            )

        machine.transition(OrchestrationState.APPROVED)

        # 8. Normalize into an OMS-ready intent.
        trading_intent = self._build_intent(signal, record, intent, mode, decision, binding)
        identity = trading_intent.orchestration_id

        # 9. Idempotency + durable persistence (narrow critical section).
        with self._lock:
            if identity in self._handed_off:
                duplicate = True
                record_id = None
                persisted = False
            elif self._repository is not None:
                try:
                    persist_outcome, record_id = self._repository.persist(
                        to_orm_trading_intent(
                            trading_intent, state=OrchestrationState.OMS_HANDOFF_READY
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - DB failure → no false success
                    logger.warning("trading-intent persistence failed: %s", exc)
                    persist_outcome = "error"
                    record_id = None
                if persist_outcome == OUTCOME_DUPLICATE:
                    duplicate = True
                    persisted = False
                elif persist_outcome == OUTCOME_INSERTED:
                    duplicate = False
                    persisted = True
                    self._remember_handed_off(identity, trading_intent)
                    machine.transition(OrchestrationState.OMS_HANDOFF_READY)
                else:
                    self._metrics.inc("persistence_failures")
                    self._metrics.record_state(OrchestrationState.FAILED.value)
                    self._metrics.record_latency(perf_counter() - start)
                    return OrchestrationResult(
                        state=OrchestrationState.FAILED,
                        intent=trading_intent,
                        risk_decision=decision,
                        reason_code="PERSISTENCE_FAILED",
                        reason="failed to durably persist the trading intent",
                    )
            else:
                duplicate = False
                persisted = False
                record_id = None
                self._remember_handed_off(identity, trading_intent)
                machine.transition(OrchestrationState.OMS_HANDOFF_READY)

        if duplicate:
            self._metrics.inc("duplicates")
            self._metrics.record_state(OrchestrationState.DUPLICATE.value)
            self._metrics.record_latency(perf_counter() - start)
            return OrchestrationResult(
                state=OrchestrationState.DUPLICATE,
                intent=trading_intent,
                risk_decision=decision,
                reason_code="DUPLICATE_ORCHESTRATION",
                reason="signal already produced a trading intent",
            )

        # 10. OMS handoff (notification only; the intent is already durable).
        handoff = self._oms_port.handoff(trading_intent)
        if not handoff.delivered:
            self._metrics.inc("oms_handoff_failures")

        self._metrics.record_state(OrchestrationState.OMS_HANDOFF_READY.value)
        self._metrics.record_latency(perf_counter() - start)
        return OrchestrationResult(
            state=OrchestrationState.OMS_HANDOFF_READY,
            intent=trading_intent,
            risk_decision=decision,
            persisted=persisted,
            record_id=record_id,
            handoff_delivered=handoff.delivered,
        )

    def process_signal_many(
        self,
        records: list[SignalRecord],
        *,
        trading_mode: str = "PAPER",
    ) -> list[OrchestrationResult]:
        """Process a batch with per-signal failure isolation."""
        results: list[OrchestrationResult] = []
        for record in records:
            try:
                results.append(self.process_signal(record, trading_mode=trading_mode))
            except Exception as exc:  # noqa: BLE001 - isolate unexpected faults
                self._metrics.inc("errors")
                logger.warning("unexpected orchestration error: %s", exc)
                results.append(
                    OrchestrationResult(
                        state=OrchestrationState.FAILED,
                        reason_code="UNEXPECTED_ERROR",
                        reason=f"{type(exc).__name__}",
                    )
                )
        return results

    # --- helpers -----------------------------------------------------------

    def _remember_handed_off(self, identity: str, intent: TradingIntent) -> None:
        """Remember a handed-off intent, bounding the in-memory idempotency cache."""
        self._handed_off[identity] = intent
        while len(self._handed_off) > self._capacity:
            self._handed_off.popitem(last=False)

    def _build_intent(
        self,
        signal: StrategySignal,
        record: SignalRecord,
        intent: RiskOrderIntent,
        mode: str,
        decision: RiskDecision,
        binding: str,
    ) -> TradingIntent:
        limit_price = _extract_limit_price(intent)
        return TradingIntent(
            correlation_id=uuid4(),
            orchestration_id=compute_orchestration_identity_key(signal, intent, mode),
            account_id=intent.account_id,
            strategy_id=signal.strategy_id,
            strategy_version=signal.strategy_version,
            strategy_config_hash=signal.strategy_config_hash,
            strategy_run_id=_parse_run_id(signal),
            signal_id=signal.signal_id,
            signal_identity_key=record.identity_key,
            instrument_id=signal.instrument_id,
            action=signal.action.value,
            quantity=intent.quantity,
            order_type=intent.order_type,
            limit_price=limit_price,
            trading_mode=mode,
            risk_decision_id=decision.decision_id,
            approval_id=decision.approval_id,
            approval_expires_at=decision.expires_at,
            binding_hash=binding,
            metadata=dict(intent.metadata),
        )

    def _reject(
        self,
        signal: StrategySignal,
        intent: RiskOrderIntent | None,
        mode: str,
        machine: OrchestrationStateMachine,
        reason_code: str,
        reason: str,
        start: float,
        *,
        persist: bool,
        decision: RiskDecision | None = None,
    ) -> OrchestrationResult:
        machine.transition(OrchestrationState.REJECTED)
        self._metrics.inc("signals_rejected")
        self._metrics.record_state(OrchestrationState.REJECTED.value)

        persisted = False
        record_id: UUID | None = None
        if persist and self._repository is not None:
            orchestration_id = compute_orchestration_identity_key(signal, intent, mode)
            record = to_orm_rejection(
                signal, intent, mode, orchestration_id,
                reason_code=reason_code, reason=reason, decision=decision,
            )
            try:
                outcome, record_id = self._repository.persist(record)
                persisted = outcome == OUTCOME_INSERTED
            except Exception as exc:  # noqa: BLE001 - best-effort rejection record
                self._metrics.inc("persistence_failures")
                logger.warning("orchestration rejection persistence failed: %s", exc)

        self._metrics.record_latency(perf_counter() - start)
        return OrchestrationResult(
            state=OrchestrationState.REJECTED,
            risk_decision=decision,
            persisted=persisted,
            record_id=record_id,
            reason_code=reason_code,
            reason=reason,
        )


def _extract_limit_price(intent: RiskOrderIntent) -> Decimal | None:
    raw = intent.metadata.get("limit_price")
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _parse_run_id(signal: StrategySignal) -> UUID | None:
    raw = run_id_from(signal)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None
