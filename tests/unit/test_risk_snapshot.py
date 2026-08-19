"""Phase 6 — risk snapshot immutability + freshness semantics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from alpha_algo_risk_engine.snapshot import RiskSnapshot

from risk_test_support import make_snapshot


def test_default_snapshot_is_fail_closed():
    snap = RiskSnapshot()
    assert snap.state_available is False
    assert snap.global_halt_active is True
    assert snap.live_trading_enabled is False


def test_snapshot_is_immutable():
    snap = make_snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.state_available = False  # type: ignore[misc]


def test_nested_snapshot_is_immutable():
    snap = make_snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.account.equity = None  # type: ignore[misc]


def test_no_max_age_never_stale():
    snap = make_snapshot(taken_at=datetime.now(UTC) - timedelta(hours=24))
    assert snap.is_stale(datetime.now(UTC)) is False


def test_stale_when_older_than_max_age():
    now = datetime.now(UTC)
    snap = make_snapshot(
        taken_at=now - timedelta(seconds=30), max_age=timedelta(seconds=5)
    )
    assert snap.is_stale(now) is True


def test_fresh_when_within_max_age():
    now = datetime.now(UTC)
    snap = make_snapshot(
        taken_at=now - timedelta(seconds=3), max_age=timedelta(seconds=5)
    )
    assert snap.is_stale(now) is False


def test_stale_requires_aware_now():
    snap = make_snapshot(max_age=timedelta(seconds=5))
    with pytest.raises(ValueError):
        snap.is_stale(datetime.now())


def test_future_dated_taken_at_is_stale():
    now = datetime.now(UTC)
    snap = make_snapshot(
        taken_at=now + timedelta(seconds=10), max_age=timedelta(seconds=5)
    )
    assert snap.is_stale(now) is True
