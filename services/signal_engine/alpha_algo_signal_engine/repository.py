"""Signal persistence via SQLAlchemy → PostgreSQL ``signals`` table.

The repository is decoupled from app wiring by receiving a ``session_factory``
(the same pattern as the Phase-3 market-data repository). Persistence is a
transactional unit of work: a signal is reported as persisted only after the
session COMMIT succeeds; on failure the transaction is rolled back and no false
SUCCESS is produced. Idempotency is enforced at the DB level via the unique
``identity_key`` constraint so a retry never creates a second record.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alpha_algo_contracts import StrategySignal
from alpha_algo_shared.db.models import Signal
from alpha_algo_signal_engine.identity import (
    code_hash_from,
    compute_signal_content_hash,
    compute_signal_identity_key,
    event_timestamp,
    run_id_from,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

OUTCOME_INSERTED = "inserted"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_CONFLICT = "conflict"


def _parse_run_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


def to_orm_signal(
    signal: StrategySignal,
    *,
    identity_key: str,
    content_hash: str,
    state: str,
    processed_at: datetime,
) -> Signal:
    """Map a validated, enriched ``StrategySignal`` to the ``Signal`` ORM model."""
    return Signal(
        id=uuid4(),
        signal_id=signal.signal_id,
        identity_key=identity_key,
        content_hash=content_hash,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        config_hash=signal.strategy_config_hash,
        code_hash=code_hash_from(signal),
        run_id=_parse_run_id(run_id_from(signal)),
        instrument_id=signal.instrument_id,
        signal_timestamp=signal.timestamp,
        action=signal.action.value,
        confidence=signal.confidence,
        reason=signal.reason,
        signal_metadata=signal.metadata,
        state=state,
        processed_at=processed_at,
    )


class SignalRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def find_by_identity(self, identity_key: str) -> Signal | None:
        session = self._session_factory()
        try:
            row = session.execute(
                select(Signal).where(Signal.identity_key == identity_key)
            ).scalar_one_or_none()
            return row
        finally:
            session.close()

    def persist(
        self,
        signal: Signal,
    ) -> str:
        """Insert one signal transactionally; return inserted/duplicate/conflict.

        The COMMIT is the transactional boundary: only after it succeeds is the
        signal considered persisted. A unique-constraint race (concurrent insert
        of the same identity) is resolved by re-querying and comparing content.
        """
        identity_key = signal.identity_key
        existing = self.find_by_identity(identity_key)
        if existing is not None:
            return (
                OUTCOME_DUPLICATE
                if existing.content_hash == signal.content_hash
                else OUTCOME_CONFLICT
            )

        session = self._session_factory()
        try:
            session.add(signal)
            session.commit()
            return OUTCOME_INSERTED
        except IntegrityError:
            session.rollback()
            # Unique-constraint race: another writer inserted the same identity.
            existing = self.find_by_identity(identity_key)
            if existing is None:
                raise
            return (
                OUTCOME_DUPLICATE
                if existing.content_hash == signal.content_hash
                else OUTCOME_CONFLICT
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
