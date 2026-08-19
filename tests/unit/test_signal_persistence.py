"""Phase 5 signal persistence: ORM mapping + transactional repository semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from signal_test_support import FakeSessionFactory, make_signal

from alpha_algo_signal_engine.identity import (
    compute_signal_content_hash,
    compute_signal_identity_key,
)
from alpha_algo_signal_engine.repository import (
    OUTCOME_CONFLICT,
    OUTCOME_DUPLICATE,
    OUTCOME_INSERTED,
    SignalRepository,
    to_orm_signal,
)


def _orm(signal, *, content_hash=None, state="persisted"):
    return to_orm_signal(
        signal,
        identity_key=compute_signal_identity_key(signal),
        content_hash=content_hash or compute_signal_content_hash(signal),
        state=state,
        processed_at=datetime.now(UTC),
    )


def test_to_orm_signal_maps_all_provenance_fields() -> None:
    sid = uuid4()
    cfg = "a" * 64
    instr = uuid4()
    run = uuid4()
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    sig = make_signal(
        strategy_id=sid,
        config_hash=cfg,
        instrument_id=instr,
        code_hash="codehash",
        run_id=run,
        timestamp=ts,
        event_timestamp=ts,
    )
    orm = _orm(sig, state="persisted")

    assert orm.signal_id == sig.signal_id
    assert orm.identity_key == compute_signal_identity_key(sig)
    assert orm.content_hash == compute_signal_content_hash(sig)
    assert orm.strategy_id == sid
    assert orm.strategy_version == "1.0.0"
    assert orm.config_hash == cfg
    assert orm.code_hash == "codehash"
    assert orm.run_id == run
    assert orm.instrument_id == instr
    assert orm.signal_timestamp == ts
    assert orm.action == "BUY"
    assert orm.state == "persisted"
    assert orm.processed_at is not None


def test_persist_inserts_and_commits() -> None:
    sig = make_signal(strategy_id=uuid4(), config_hash="a" * 64)
    factory = FakeSessionFactory()
    repo = SignalRepository(factory)

    assert repo.persist(_orm(sig)) == OUTCOME_INSERTED
    assert any(s.committed for s in factory.sessions)
    assert any(len(s.added) == 1 for s in factory.sessions)


def test_persist_duplicate_returns_duplicate() -> None:
    sig = make_signal(strategy_id=uuid4(), config_hash="a" * 64)
    existing = _orm(sig)
    factory = FakeSessionFactory(find_results=[existing])
    repo = SignalRepository(factory)

    assert repo.persist(_orm(sig)) == OUTCOME_DUPLICATE


def test_persist_conflict_returns_conflict() -> None:
    sig = make_signal(strategy_id=uuid4(), config_hash="a" * 64)
    existing = _orm(sig, content_hash="different-content-hash")
    factory = FakeSessionFactory(find_results=[existing])
    repo = SignalRepository(factory)

    assert repo.persist(_orm(sig)) == OUTCOME_CONFLICT


def test_persist_rolls_back_and_reraises_on_failure() -> None:
    sig = make_signal(strategy_id=uuid4(), config_hash="a" * 64)
    factory = FakeSessionFactory(commit_raises=RuntimeError("db unavailable"))
    repo = SignalRepository(factory)

    with pytest.raises(RuntimeError):
        repo.persist(_orm(sig))
    assert any(s.rolled_back for s in factory.sessions)
    # No false SUCCESS: nothing was committed.
    assert not any(s.committed for s in factory.sessions)
