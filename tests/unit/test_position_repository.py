"""Phase 11 — repository mapper + transaction-boundary tests.

Live PostgreSQL is deferred (no Docker here); the SQLAlchemy repository's pure
mapper/builders are tested directly, and the transactional semantics (commit /
rollback / unique-constraint) are exercised through the in-memory double that
mirrors the durable behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_position_engine.contracts import PositionEventType, PositionStatus
from alpha_algo_position_engine.engine import PositionEventData
from alpha_algo_position_engine.errors import DuplicateApplyError, PositionPersistenceError
from alpha_algo_position_engine.identity import fill_content_hash
from alpha_algo_position_engine.repository import PositionRepository, to_state
from alpha_algo_shared.db.models.safety import PositionEvent
from alpha_algo_shared.db.models.trading import Position

from position_test_support import InMemoryPositionRepository, make_fill


def _state():
    return dict(
        position_id=None,
        strategy_run_id=uuid4(),
        instrument_id=uuid4(),
        trading_mode="PAPER",
        account_id=uuid4(),
        quantity=150,
        average_price=Decimal("103.3333"),
        status=PositionStatus.OPEN,
        opened_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        closed_at=None,
        last_execution_id="exec-1",
    )


def test_to_state_none_returns_none():
    assert to_state(None) is None


def test_to_state_normalizes_legacy_lowercase_status():
    from alpha_algo_position_engine.contracts import PositionState

    s = PositionState(**_state())
    row = PositionRepository._new_position_row(s)
    row.status = "open"  # legacy server_default value
    assert to_state(row).status == PositionStatus.OPEN
    row.status = "closed"
    assert to_state(row).status == PositionStatus.CLOSED


def test_new_position_row_and_roundtrip():
    from alpha_algo_position_engine.contracts import PositionState

    s = PositionState(**_state())
    row = PositionRepository._new_position_row(s)
    assert row.strategy_run_id == s.strategy_run_id
    assert row.quantity == 150
    assert row.average_price == Decimal("103.3333")
    assert row.status == "OPEN"
    assert row.last_execution_id == "exec-1"

    roundtripped = to_state(row)
    assert roundtripped.quantity == s.quantity
    assert roundtripped.average_price == s.average_price
    assert roundtripped.status == s.status
    assert roundtripped.last_execution_id == s.last_execution_id


def test_apply_state_updates_all_fields():
    from alpha_algo_position_engine.contracts import PositionState

    row = PositionRepository._new_position_row(PositionState(**_state()))
    changed = PositionState(**{**_state(), "quantity": 0, "status": PositionStatus.CLOSED, "closed_at": datetime(2026, 8, 20, 11, 0, tzinfo=UTC), "last_execution_id": "exec-2"})
    PositionRepository._apply_state(row, changed)
    assert row.quantity == 0
    assert row.status == "CLOSED"
    assert row.closed_at is not None
    assert row.last_execution_id == "exec-2"


def test_new_event_row_carries_identity_and_hash():
    event = PositionEventData(
        event_type=PositionEventType.POSITION_OPENED,
        quantity_before=0,
        quantity_after=100,
        execution_id="exec-1",
        content_hash="h" * 64,
        occurred_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        reason="fill",
    )
    row = PositionRepository._new_event_row(uuid4(), event)
    assert row.source_event_id == "exec-1"
    assert row.event_type == "POSITION_OPENED"
    assert row.quantity_before == 0
    assert row.quantity_after == 100
    assert row.event_payload["_content_hash"] == "h" * 64


def test_inmemory_duplicate_apply_raises_unique_constraint():
    from alpha_algo_position_engine.contracts import PositionIdentity, PositionState
    from alpha_algo_position_engine.identity import build_position_identity

    repo = InMemoryPositionRepository()
    fill = make_fill(execution_id="e1", side="BUY", quantity="100", price="100")
    identity = build_position_identity(strategy_run_id=fill.strategy_run_id, instrument_id=fill.instrument_id, trading_mode=fill.trading_mode)

    state = PositionState(
        position_id=None, strategy_run_id=fill.strategy_run_id, instrument_id=fill.instrument_id,
        trading_mode="PAPER", account_id=fill.account_id, quantity=100,
        average_price=Decimal("100"), status=PositionStatus.OPEN,
        opened_at=fill.occurred_at, closed_at=None, last_execution_id="e1",
    )
    event = PositionEventData(PositionEventType.POSITION_OPENED, 0, 100, "e1", fill_content_hash(fill), fill.occurred_at, "fill")

    repo.persist_apply(identity=identity, state=state, event=event, fill=fill)
    with pytest.raises(DuplicateApplyError):
        repo.persist_apply(identity=identity, state=state, event=event, fill=fill)


def test_inmemory_failure_rolls_back_without_mutation():
    repo = InMemoryPositionRepository()
    repo.fail_next_apply = True
    fill = make_fill(side="BUY", quantity="100", price="100")
    from alpha_algo_position_engine.contracts import PositionIdentity, PositionState
    from alpha_algo_position_engine.identity import build_position_identity

    identity = build_position_identity(strategy_run_id=fill.strategy_run_id, instrument_id=fill.instrument_id, trading_mode=fill.trading_mode)
    state = PositionState(None, fill.strategy_run_id, fill.instrument_id, "PAPER", fill.account_id, 100, Decimal("100"), PositionStatus.OPEN, fill.occurred_at, None, "e1")
    event = PositionEventData(PositionEventType.POSITION_OPENED, 0, 100, "e1", fill_content_hash(fill), fill.occurred_at, "fill")

    with pytest.raises(PositionPersistenceError):
        repo.persist_apply(identity=identity, state=state, event=event, fill=fill)

    assert identity.as_tuple() not in repo.positions
    assert "e1" not in repo.events
    assert repo.applied == []
