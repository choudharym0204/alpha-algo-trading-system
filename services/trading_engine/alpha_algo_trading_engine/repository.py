"""Transactional persistence of orchestration outcomes to ``trading_intents``
(Phase 7). COMMIT is the boundary of truth; idempotency is keyed on
``orchestration_id`` (unique). A concurrent duplicate insert is back-stopped by
the unique constraint, and the in-memory find-then-insert is only an optimization.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alpha_algo_contracts import RiskDecision, StrategySignal
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_shared.db.models.trading import TradingIntentRecord
from alpha_algo_signal_engine.identity import run_id_from
from alpha_algo_trading_engine.intent import TradingIntent
from alpha_algo_trading_engine.state import OrchestrationState

OUTCOME_INSERTED = "inserted"
OUTCOME_DUPLICATE = "duplicate"


def _parse_run_id(signal: StrategySignal) -> UUID | None:
    raw = run_id_from(signal)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def to_orm_trading_intent(
    intent: TradingIntent,
    *,
    state: OrchestrationState,
    reason_code: str | None = None,
    reason: str | None = None,
) -> TradingIntentRecord:
    return TradingIntentRecord(
        orchestration_id=intent.orchestration_id,
        correlation_id=str(intent.correlation_id),
        signal_id=intent.signal_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        strategy_config_hash=intent.strategy_config_hash,
        strategy_run_id=intent.strategy_run_id,
        account_id=intent.account_id,
        instrument_id=intent.instrument_id,
        action=intent.action,
        order_type=intent.order_type,
        quantity=intent.quantity,
        limit_price=intent.limit_price,
        trading_mode=intent.trading_mode,
        risk_decision_id=intent.risk_decision_id,
        approval_id=str(intent.approval_id),
        approval_expires_at=intent.approval_expires_at,
        binding_hash=intent.binding_hash,
        state=state.value,
        reason_code=reason_code,
        reason=reason,
        intent_metadata=intent.metadata,
    )


def to_orm_rejection(
    signal: StrategySignal,
    intent: RiskOrderIntent | None,
    trading_mode: str,
    orchestration_id: str,
    *,
    reason_code: str,
    reason: str,
    decision: RiskDecision | None = None,
) -> TradingIntentRecord:
    return TradingIntentRecord(
        orchestration_id=orchestration_id,
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        strategy_config_hash=signal.strategy_config_hash,
        strategy_run_id=_parse_run_id(signal),
        account_id=intent.account_id if intent is not None else None,
        instrument_id=signal.instrument_id,
        action=signal.action.value,
        order_type=intent.order_type if intent is not None else None,
        quantity=intent.quantity if intent is not None else None,
        trading_mode=trading_mode,
        risk_decision_id=decision.decision_id if decision is not None else None,
        state=OrchestrationState.REJECTED.value,
        reason_code=reason_code,
        reason=reason,
    )


def _find_by_orchestration_id(session, orchestration_id: str) -> TradingIntentRecord | None:
    return session.execute(
        select(TradingIntentRecord).where(
            TradingIntentRecord.orchestration_id == orchestration_id
        )
    ).scalar_one_or_none()


class TradingIntentRepository:
    """Persists a ``TradingIntentRecord``. COMMIT is the boundary of truth."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def persist(self, record: TradingIntentRecord) -> tuple[str, UUID | None]:
        session = self._session_factory()
        try:
            existing = _find_by_orchestration_id(session, record.orchestration_id)
        finally:
            session.close()

        if existing is not None:
            return OUTCOME_DUPLICATE, existing.id

        session = self._session_factory()
        try:
            session.add(record)
            session.commit()
            return OUTCOME_INSERTED, record.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
