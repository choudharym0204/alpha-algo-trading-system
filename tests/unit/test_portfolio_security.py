"""Phase 12 — security / LIVE-safety / isolation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from alpha_algo_portfolio_engine.engine import PortfolioEngine
from alpha_algo_portfolio_engine.errors import (
    PortfolioModeError,
    PortfolioValidationError,
)

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
    make_position,
    make_price,
)

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "services" / "portfolio_engine" / "alpha_algo_portfolio_engine"


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def _priced_inputs(account_id=None):
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100)
    return make_inputs(
        account_id=account_id,
        positions=(pos,),
        funds=make_funds(),
        prices={iid: make_price(iid, "100")},
    )


def test_live_mode_cannot_be_enabled():
    engine = PortfolioEngine(repository=InMemoryPortfolioRepository(), global_halt_active=lambda: False)
    with pytest.raises(PortfolioModeError):
        engine.snapshot(make_inputs(trading_mode="LIVE"), _t())


def test_unknown_mode_fails_closed():
    engine = PortfolioEngine(repository=InMemoryPortfolioRepository(), global_halt_active=lambda: False)
    with pytest.raises(PortfolioModeError):
        engine.compute(make_inputs(trading_mode="HFT"), now=_t())


def test_global_halt_blocks_computation():
    engine = PortfolioEngine(repository=InMemoryPortfolioRepository(), global_halt_active=lambda: True)
    with pytest.raises(PortfolioValidationError):
        engine.compute(_priced_inputs(), now=_t())


def test_cross_account_leakage_impossible():
    repo = InMemoryPortfolioRepository()
    engine = PortfolioEngine(repository=repo, global_halt_active=lambda: False)
    a, b = uuid4(), uuid4()
    engine.snapshot(_priced_inputs(account_id=a), _t())

    # Reading account B must not return account A's snapshot.
    assert engine.get_latest(account_id=b, trading_mode="PAPER") is None
    assert engine.list_snapshots(account_id=b, trading_mode="PAPER") == []


def test_no_broker_sdk_import_in_portfolio_package():
    forbidden = ("kiteconnect", "upstox", "smartapi", "broker_integration", "alpha_algo_broker")
    violations = []
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append((path.name, token))
    assert violations == [], f"portfolio engine leaks broker dependency: {violations}"


def test_no_secret_material_in_portfolio_package():
    secret_markers = ("api_key", "access_token", "password", "secret", "client_id", "user_id")
    hits = []
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in secret_markers:
            if marker in text:
                hits.append((path.name, marker))
    assert hits == [], f"portfolio engine contains secret markers: {hits}"


def test_no_pnl_implementation_in_portfolio_package():
    # Phase 12 must not implement P&L (Phase 13 boundary).
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        # realized_pnl/unrealized_pnl appear only as delegated placeholders,
        # never as computed values. Assert no computation.
        assert "realized_pnl =" not in text.replace(" ", "")
        assert "unrealized_pnl =" not in text.replace(" ", "")
