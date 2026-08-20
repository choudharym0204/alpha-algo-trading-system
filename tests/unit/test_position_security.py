"""Phase 11 — security / LIVE-safety / broker-isolation tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from alpha_algo_position_engine.engine import PositionEngine
from alpha_algo_position_engine.errors import PositionModeError, PositionValidationError

from position_test_support import InMemoryPositionRepository, make_fill

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "services" / "position_engine" / "alpha_algo_position_engine"


def _source_text() -> str:
    parts = []
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_live_mode_is_rejected_fail_closed():
    engine = PositionEngine(repository=InMemoryPositionRepository(), global_halt_active=lambda: False)
    with pytest.raises(PositionModeError):
        engine.apply_fill(make_fill(trading_mode="LIVE", side="BUY", quantity="100", price="100"))


def test_unknown_mode_is_rejected():
    engine = PositionEngine(repository=InMemoryPositionRepository(), global_halt_active=lambda: False)
    with pytest.raises(PositionModeError):
        engine.apply_fill(make_fill(trading_mode="SANDBOX", side="BUY", quantity="100", price="100"))


def test_global_halt_blocks_by_default():
    # No global_halt_active override => fail-closed default (halt active).
    engine = PositionEngine(repository=InMemoryPositionRepository())
    with pytest.raises(PositionValidationError):
        engine.apply_fill(make_fill(side="BUY", quantity="100", price="100"))


def test_no_broker_sdk_in_position_engine_source():
    src = _source_text()
    for forbidden in ("zerodha", "upstox", "angel", "kiteconnect", "smartapi", "pyupstox", "kite"):
        assert forbidden not in src.lower()


def test_no_broker_snapshot_overwrite_path():
    """The engine must expose no mutation path that ingests a broker snapshot."""
    forbidden_methods = [
        "apply_broker_snapshot",
        "ingest_broker_position",
        "sync_broker_position",
        "overwrite_from_broker",
        "replace_from_broker",
    ]
    public = [name for name in dir(PositionEngine) if not name.startswith("_")]
    for m in forbidden_methods:
        assert m not in public

    # The engine's mutation entry point is apply_fill (normalized fill) only.
    mutators = [n for n in public if n.startswith("apply") or n.startswith("ingest") or n.startswith("sync")]
    assert mutators == ["apply_fill"]


def test_no_credentials_in_position_engine_source():
    src = _source_text()
    for secret in ("api_key", "access_token", "secret_key", "password=", "apikey"):
        assert secret not in src.lower()


def test_paper_mode_is_supported():
    engine = PositionEngine(repository=InMemoryPositionRepository(), global_halt_active=lambda: False)
    result = engine.apply_fill(make_fill(trading_mode="PAPER", side="BUY", quantity="100", price="100"))
    assert result.snapshot.quantity == 100


def test_backtest_mode_is_supported():
    engine = PositionEngine(repository=InMemoryPositionRepository(), global_halt_active=lambda: False)
    result = engine.apply_fill(make_fill(trading_mode="BACKTEST", side="BUY", quantity="100", price="100"))
    assert result.snapshot.quantity == 100
