"""Phase 5 signal identity + content hashing (deterministic, not random)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from signal_test_support import make_signal

from alpha_algo_contracts import SignalAction
from alpha_algo_signal_engine.identity import (
    code_hash_from,
    compute_signal_content_hash,
    compute_signal_identity_key,
    event_timestamp,
    run_id_from,
)


def test_identity_key_is_deterministic() -> None:
    sid = uuid4()
    cfg = "a" * 64
    instr = uuid4()
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    a = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts)
    b = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts)
    assert compute_signal_identity_key(a) == compute_signal_identity_key(b)


def test_identity_key_not_derived_from_random_signal_id() -> None:
    sid = uuid4()
    cfg = "a" * 64
    instr = uuid4()
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    a = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts)
    b = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts)
    assert a.signal_id != b.signal_id
    assert compute_signal_identity_key(a) == compute_signal_identity_key(b)


def test_identity_key_changes_per_attribute() -> None:
    sid = uuid4()
    cfg = "a" * 64
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    base = make_signal(
        strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, instrument_id=uuid4()
    )
    base_key = compute_signal_identity_key(base)

    assert compute_signal_identity_key(make_signal(strategy_id=uuid4(), config_hash=cfg, timestamp=ts, event_timestamp=ts)) != base_key
    assert compute_signal_identity_key(make_signal(strategy_id=sid, version="2.0.0", config_hash=cfg, timestamp=ts, event_timestamp=ts)) != base_key
    assert compute_signal_identity_key(make_signal(strategy_id=sid, config_hash="b" * 64, timestamp=ts, event_timestamp=ts)) != base_key
    assert compute_signal_identity_key(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, instrument_id=uuid4())) != base_key
    assert compute_signal_identity_key(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, action=SignalAction.SELL)) != base_key
    assert compute_signal_identity_key(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts + timedelta(seconds=1))) != base_key


def test_content_hash_is_deterministic() -> None:
    sid = uuid4()
    cfg = "a" * 64
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    a = make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts)
    b = make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts)
    assert compute_signal_content_hash(a) == compute_signal_content_hash(b)


def test_content_hash_stable_across_replay_with_fresh_timestamp() -> None:
    sid = uuid4()
    cfg = "a" * 64
    instr = uuid4()
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    # Same event (same event_timestamp), but the strategy regenerated the signal
    # with a fresh signal.timestamp → identity + content hash must stay identical
    # so a replay is classified DUPLICATE, not a false CONFLICT.
    a = make_signal(strategy_id=sid, config_hash=cfg, instrument_id=instr, timestamp=ts, event_timestamp=ts)
    b = make_signal(
        strategy_id=sid,
        config_hash=cfg,
        instrument_id=instr,
        timestamp=ts + timedelta(seconds=7),
        event_timestamp=ts,
    )
    assert compute_signal_identity_key(a) == compute_signal_identity_key(b)
    assert compute_signal_content_hash(a) == compute_signal_content_hash(b)


def test_content_hash_changes_on_content_change() -> None:
    sid = uuid4()
    cfg = "a" * 64
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    base = make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts)
    base_hash = compute_signal_content_hash(base)

    assert compute_signal_content_hash(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, confidence=Decimal("0.9"))) != base_hash
    assert compute_signal_content_hash(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, reason="different")) != base_hash
    # signal.timestamp is volatile across a replay; content_hash is anchored to
    # the authoritative event_timestamp, so a fresh timestamp must NOT change it.
    assert compute_signal_content_hash(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts + timedelta(seconds=1), event_timestamp=ts)) == base_hash
    assert compute_signal_content_hash(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts + timedelta(seconds=1))) != base_hash
    assert compute_signal_content_hash(make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=ts, metadata={"x": 1})) != base_hash


def test_event_timestamp_reads_metadata_then_falls_back() -> None:
    sid = uuid4()
    cfg = "a" * 64
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    marker = datetime(2026, 1, 2, tzinfo=UTC)
    with_marker = make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts, event_timestamp=marker)
    assert event_timestamp(with_marker) == marker

    # Without the marker, falls back to signal.timestamp.
    without = make_signal(strategy_id=sid, config_hash=cfg, timestamp=ts)
    without.metadata.pop("event_timestamp")
    assert event_timestamp(without) == ts


def test_code_hash_and_run_id_extraction() -> None:
    sid = uuid4()
    cfg = "a" * 64
    run = uuid4()
    sig = make_signal(strategy_id=sid, config_hash=cfg, code_hash="codehash123", run_id=run)
    assert code_hash_from(sig) == "codehash123"
    assert run_id_from(sig) == str(run)

    plain = make_signal(strategy_id=sid, config_hash=cfg)
    assert code_hash_from(plain) is None
    assert run_id_from(plain) is None
