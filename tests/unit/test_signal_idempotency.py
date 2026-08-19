"""Phase 5 signal idempotency (new / duplicate / conflict) + bounded LRU."""

from __future__ import annotations

import pytest

from alpha_algo_signal_engine.idempotency import (
    OUTCOME_CONFLICT,
    OUTCOME_DUPLICATE,
    OUTCOME_NEW,
    SignalIdempotency,
)


def test_new_then_record_then_duplicate_then_conflict() -> None:
    d = SignalIdempotency()
    assert d.check("key-1", "hash-A") == OUTCOME_NEW
    d.record("key-1", "hash-A")
    assert d.check("key-1", "hash-A") == OUTCOME_DUPLICATE
    assert d.check("key-1", "hash-B") == OUTCOME_CONFLICT


def test_check_does_not_record() -> None:
    d = SignalIdempotency()
    assert d.check("key-1", "hash-A") == OUTCOME_NEW
    # Not recorded → still NEW until record() is called.
    assert d.check("key-1", "hash-A") == OUTCOME_NEW


def test_distinct_keys_are_independent() -> None:
    d = SignalIdempotency()
    assert d.check("key-1", "hash-A") == OUTCOME_NEW
    d.record("key-1", "hash-A")
    assert d.check("key-2", "hash-A") == OUTCOME_NEW
    assert d.check("key-1", "hash-A") == OUTCOME_DUPLICATE


def test_bounded_lru_evicts_oldest() -> None:
    d = SignalIdempotency(maxsize=2)
    d.record("k1", "h1")
    d.record("k2", "h2")
    d.record("k3", "h3")  # evicts k1
    assert len(d) == 2
    assert d.check("k1", "h1") == OUTCOME_NEW  # was evicted


def test_rejects_invalid_maxsize() -> None:
    with pytest.raises(ValueError):
        SignalIdempotency(maxsize=0)
