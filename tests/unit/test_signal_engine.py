"""Phase 5 SignalEngine end-to-end ingest flow (validation → identity → persist)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from signal_test_support import FakeDirectory, FakeSessionFactory, make_record, make_signal

from alpha_algo_signal_engine.errors import TradingModeError
from alpha_algo_signal_engine.identity import (
    compute_signal_content_hash,
    compute_signal_identity_key,
)
from alpha_algo_signal_engine.idempotency import OUTCOME_NEW
from alpha_algo_signal_engine.repository import SignalRepository
from alpha_algo_signal_engine.service import SignalEngine
from alpha_algo_signal_engine.state import SignalState


def _engine(records=None, session_factory=None, **kwargs):
    directory = FakeDirectory(records)
    repo = SignalRepository(session_factory or FakeSessionFactory())
    return SignalEngine(directory=directory, repository=repo, **kwargs)


def test_valid_signal_persists() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine([make_record(sid, config_hash=cfg)])
    result = engine.ingest(make_signal(strategy_id=sid, config_hash=cfg), trading_mode="PAPER")

    assert result.state == SignalState.PERSISTED
    assert result.persisted is True
    assert result.identity_key is not None
    assert result.record_id is not None
    assert engine.metrics.signals_persisted == 1
    assert engine.metrics.signals_accepted == 1
    assert engine.metrics.signals_received == 1


def test_duplicate_replay_is_idempotent() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine([make_record(sid, config_hash=cfg)])
    sig = make_signal(strategy_id=sid, config_hash=cfg)

    assert engine.ingest(sig, trading_mode="PAPER").state == SignalState.PERSISTED
    second = engine.ingest(sig, trading_mode="PAPER")
    assert second.state == SignalState.DUPLICATE
    assert second.persisted is False
    assert engine.metrics.signals_persisted == 1
    assert engine.metrics.signals_duplicate == 1


def test_same_identity_different_content_is_conflict() -> None:
    sid = uuid4()
    cfg = "a" * 64
    instr = uuid4()
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    engine = _engine([make_record(sid, config_hash=cfg)])

    a = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts, reason="buy now")
    b = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts, reason="different")

    assert engine.ingest(a, trading_mode="PAPER").state == SignalState.PERSISTED
    conflict = engine.ingest(b, trading_mode="PAPER")
    assert conflict.state == SignalState.CONFLICT
    assert engine.metrics.signals_conflict == 1


def test_backtest_and_paper_accepted() -> None:
    sid = uuid4()
    cfg = "a" * 64
    for mode in ("BACKTEST", "PAPER", "backtest", "paper"):
        engine = _engine([make_record(sid, config_hash=cfg)])
        result = engine.ingest(make_signal(strategy_id=sid, config_hash=cfg), trading_mode=mode)
        assert result.state == SignalState.PERSISTED


def test_live_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine([make_record(sid, config_hash=cfg)])
    with pytest.raises(TradingModeError):
        engine.ingest(make_signal(strategy_id=sid, config_hash=cfg), trading_mode="LIVE")


def test_invalid_signal_rejected_not_crashed() -> None:
    engine = _engine([])  # unknown strategy
    result = engine.ingest(make_signal(strategy_id=uuid4(), config_hash="a" * 64), trading_mode="PAPER")
    assert result.state == SignalState.REJECTED
    assert result.reason == "unknown_strategy"
    assert engine.metrics.signals_rejected == 1


def test_expired_signal_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    engine = _engine(
        [make_record(sid, config_hash=cfg)],
        clock=lambda: datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        max_signal_age=timedelta(seconds=5),
    )
    result = engine.ingest(
        make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts),
        trading_mode="PAPER",
    )
    assert result.state == SignalState.EXPIRED
    assert engine.metrics.signals_expired == 1


def test_persistence_failure_no_false_success() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine(
        [make_record(sid, config_hash=cfg)],
        session_factory=FakeSessionFactory(commit_raises=RuntimeError("db down")),
    )
    result = engine.ingest(make_signal(strategy_id=sid, config_hash=cfg), trading_mode="PAPER")
    assert result.state == SignalState.ACCEPTED
    assert result.persisted is False
    assert result.reason == "persistence_failure"
    assert engine.metrics.persistence_failures == 1
    assert engine.metrics.signals_persisted == 0


def test_retry_after_db_failure_persists() -> None:
    sid = uuid4()
    cfg = "a" * 64
    sig = make_signal(strategy_id=sid, config_hash=cfg)

    failing = _engine(
        [make_record(sid, config_hash=cfg)],
        session_factory=FakeSessionFactory(commit_raises=RuntimeError("db down")),
    )
    first = failing.ingest(sig, trading_mode="PAPER")
    assert first.state == SignalState.ACCEPTED

    # DB recovered → retry persists instead of being swallowed as a duplicate.
    healthy = _engine([make_record(sid, config_hash=cfg)], session_factory=FakeSessionFactory())
    second = healthy.ingest(sig, trading_mode="PAPER")
    assert second.state == SignalState.PERSISTED


def test_failed_persist_does_not_poison_idempotency() -> None:
    sid = uuid4()
    cfg = "a" * 64
    sig = make_signal(strategy_id=sid, config_hash=cfg)
    engine = _engine(
        [make_record(sid, config_hash=cfg)],
        session_factory=FakeSessionFactory(commit_raises=RuntimeError("db down")),
    )
    engine.ingest(sig, trading_mode="PAPER")
    assert engine.idempotency.check(
        compute_signal_identity_key(sig), compute_signal_content_hash(sig)
    ) == OUTCOME_NEW


def test_consumer_fan_out_on_persist() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine([make_record(sid, config_hash=cfg)])
    received: list = []
    engine.add_consumer(received.append)

    engine.ingest(make_signal(strategy_id=sid, config_hash=cfg), trading_mode="PAPER")
    assert len(received) == 1
    assert received[0].state == SignalState.PERSISTED
    assert received[0].identity_key is not None


def test_ingest_many_isolates_bad_signal() -> None:
    sid = uuid4()
    cfg = "a" * 64
    engine = _engine([make_record(sid, config_hash=cfg)])
    good_a = make_signal(strategy_id=sid, config_hash=cfg)
    bad = make_signal(strategy_id=uuid4(), config_hash=cfg)  # unknown strategy
    good_c = make_signal(strategy_id=sid, config_hash=cfg)

    results = engine.ingest_many([good_a, bad, good_c], trading_mode="PAPER")
    assert [r.state for r in results] == [
        SignalState.PERSISTED,
        SignalState.REJECTED,
        SignalState.PERSISTED,
    ]
