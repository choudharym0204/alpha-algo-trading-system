"""Transactional persistence of risk decisions to ``risk_events`` (Phase 6).

Idempotency is keyed on ``identity_key`` (the stable risk identity derived from
the signal + order intent + trading mode), backed by a unique constraint on
``risk_events.identity_key``. The in-memory find is an optimization; the unique
constraint is the cross-process backstop (a concurrent duplicate insert raises,
which the caller treats as non-committed).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alpha_algo_contracts import RiskDecision
from alpha_algo_shared.db.models.safety import RiskEvent

OUTCOME_INSERTED = "inserted"
OUTCOME_DUPLICATE = "duplicate"


def to_orm_risk_event(
    decision: RiskDecision,
    *,
    account_id: UUID | None = None,
    trading_mode: str | None = None,
    snapshot_id: UUID | None = None,
    identity_key: str | None = None,
) -> RiskEvent:
    return RiskEvent(
        decision_id=decision.decision_id,
        strategy_id=decision.strategy_id,
        signal_id=decision.signal_id,
        instrument_id=decision.instrument_id,
        account_id=account_id,
        decision=decision.decision.value,
        reason_code=decision.reason_code,
        reason=decision.reason,
        approval_id=str(decision.approval_id) if decision.approval_id is not None else None,
        expires_at=decision.expires_at,
        evaluated_at=decision.evaluated_at,
        trading_mode=trading_mode,
        rule_id=decision.rule_id,
        binding_hash=decision.binding_hash,
        identity_key=identity_key,
        snapshot_id=snapshot_id,
        risk_metadata=decision.metadata,
    )


def _find_by_identity_key(session, identity_key: str) -> RiskEvent | None:
    if identity_key is None:
        return None
    return session.execute(
        select(RiskEvent).where(RiskEvent.identity_key == identity_key)
    ).scalar_one_or_none()


class RiskEventRepository:
    """Persists RiskDecision as a RiskEvent. COMMIT is the boundary of truth."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def persist(self, event: RiskEvent) -> tuple[str, UUID | None]:
        # Find session (pure lookup, keyed on the stable identity key).
        session = self._session_factory()
        try:
            existing = _find_by_identity_key(session, event.identity_key)
        finally:
            session.close()

        if existing is not None:
            return OUTCOME_DUPLICATE, existing.id

        # Persist session (COMMIT is the only success signal). A concurrent
        # duplicate insert raises on the unique constraint; let it propagate so
        # the caller treats it as non-committed (no fan-out).
        session = self._session_factory()
        try:
            session.add(event)
            session.commit()
            return OUTCOME_INSERTED, event.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
