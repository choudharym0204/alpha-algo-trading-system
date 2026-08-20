"""Phase 13 — security / LIVE-safety / isolation tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from alpha_algo_pnl_engine.engine import PnlEngine
from alpha_algo_pnl_engine.errors import PnlModeError, PnlValidationError

from pnl_test_support import InMemoryPnlRepository, make_fill, make_position

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "services" / "pnl_engine" / "alpha_algo_pnl_engine"


def _engine(repo=None, halt=False):
    return PnlEngine(repository=repo or InMemoryPnlRepository(), global_halt_active=lambda: halt)


def test_live_mode_cannot_be_enabled():
    engine = _engine()
    fill = make_fill(trading_mode="LIVE", side="BUY")
    with pytest.raises(PnlModeError):
        engine.record_fill(fill=fill, position_before=make_position(quantity=0))


def test_unknown_mode_fails_closed():
    engine = _engine()
    fill = make_fill(trading_mode="HFT", side="BUY")
    with pytest.raises(PnlModeError):
        engine.record_fill(fill=fill, position_before=make_position(quantity=0))


def test_halt_blocks_pnl():
    engine = _engine(halt=True)
    fill = make_fill(side="BUY")
    with pytest.raises(PnlValidationError):
        engine.record_fill(fill=fill, position_before=make_position(quantity=0))


def test_no_mutation_path_for_historical_facts():
    # Historical accounting events are append-only: no update/delete SQL.
    repo = Path(_PACKAGE_DIR / "repository.py").read_text(encoding="utf-8")
    assert "update(" not in repo
    assert "delete(" not in repo
    assert "session.execute(update" not in repo
    assert "session.execute(delete" not in repo


def test_no_broker_sdk_import():
    forbidden = ("kiteconnect", "upstox", "smartapi", "broker_integration", "alpha_algo_broker")
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} leaks broker dependency: {token}"


def test_no_secret_material():
    markers = ("api_key", "access_token", "password", "secret", "client_id", "user_id")
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in text, f"{path.name} contains secret marker: {marker}"


def test_account_isolation_in_event_queries():
    repo = InMemoryPnlRepository()
    engine = _engine(repo)
    acc_a, acc_b = uuid4(), uuid4()

    engine.record_fill(
        fill=make_fill(account_id=acc_a, side="SELL", quantity="10", price="120", execution_id="a"),
        position_before=make_position(account_id=acc_a, quantity=100, average_price="100"),
    )
    engine.record_fill(
        fill=make_fill(account_id=acc_b, side="SELL", quantity="10", price="130", execution_id="b"),
        position_before=make_position(account_id=acc_b, quantity=100, average_price="100"),
    )

    only_a = repo.list_events(account_id=acc_a)
    assert len(only_a) == 1
    assert only_a[0].account_id == acc_a


def test_strategy_isolation_in_event_queries():
    repo = InMemoryPnlRepository()
    engine = _engine(repo)
    acc = uuid4()
    s1, s2 = uuid4(), uuid4()

    engine.record_fill(
        fill=make_fill(account_id=acc, strategy_run_id=s1, side="SELL", quantity="10", price="120", execution_id="a"),
        position_before=make_position(account_id=acc, strategy_run_id=s1, quantity=100, average_price="100"),
    )
    engine.record_fill(
        fill=make_fill(account_id=acc, strategy_run_id=s2, side="SELL", quantity="10", price="130", execution_id="b"),
        position_before=make_position(account_id=acc, strategy_run_id=s2, quantity=100, average_price="100"),
    )

    only_s1 = repo.list_events(strategy_run_id=s1)
    assert len(only_s1) == 1
    assert only_s1[0].strategy_run_id == s1
