"""Phase 14 — security / LIVE-safety / isolation tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from alpha_algo_reconciliation_engine.engine import ReconciliationEngine
from alpha_algo_reconciliation_engine.errors import (
    ReconciliationModeError,
    ReconciliationValidationError,
)

from reconciliation_test_support import (
    InMemoryReconciliationRepository,
)

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "services" / "reconciliation_engine" / "alpha_algo_reconciliation_engine"


def _engine(repo=None, halt=False):
    return ReconciliationEngine(repository=repo or InMemoryReconciliationRepository(), global_halt_active=lambda: halt)


def test_live_mode_cannot_be_enabled():
    engine = _engine()
    from alpha_algo_reconciliation_engine.contracts import ReconciliationScope
    with pytest.raises(ReconciliationModeError):
        engine.run(scope=ReconciliationScope(account_id=uuid4(), broker="PAPER", trading_mode="LIVE"), inputs=_empty_inputs())


def test_halt_blocks_reconciliation():
    engine = _engine(halt=True)
    from alpha_algo_reconciliation_engine.contracts import ReconciliationScope
    with pytest.raises(ReconciliationValidationError):
        engine.run(scope=ReconciliationScope(account_id=uuid4(), broker="PAPER", trading_mode="PAPER"), inputs=_empty_inputs())


def test_no_broker_specific_branch():
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("zerodha", "upstox", "angel_one", "angel one"):
            assert token not in text.lower(), f"{path.name} contains broker-specific branch: {token}"


def test_no_broker_sdk_import():
    forbidden = ("kiteconnect", "smartapi", "alpha_algo_broker", "broker_integration")
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


def test_no_domain_engine_bypass():
    # Reconciliation must not import/mutate Position/P&L/Portfolio engines.
    forbidden = ("alpha_algo_position_engine", "alpha_algo_pnl_engine", "alpha_algo_portfolio_engine")
    for path in _PACKAGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} bypasses a domain engine: {token}"


def test_no_mutation_path_in_repository():
    repo = (_PACKAGE_DIR / "repository.py").read_text(encoding="utf-8")
    assert "update(" not in repo
    assert "delete(" not in repo
    assert "session.execute(update" not in repo
    assert "session.execute(delete" not in repo


def _empty_inputs():
    from alpha_algo_reconciliation_engine.contracts import ReconciliationInputs
    return ReconciliationInputs()
