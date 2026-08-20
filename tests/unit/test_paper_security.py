from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import alpha_algo_paper_runtime as pkg
from alpha_algo_paper_trading import PaperBrokerAdapter
from alpha_algo_paper_runtime import (
    LiveTradingDisabledError,
    resolve_provider,
)

PACKAGE_DIR = Path(pkg.__file__).resolve().parent

FORBIDDEN_BROKER_TOKENS = ("zerodha", "upstox", "angel_one", "angel one")
FORBIDDEN_ENGINE_IMPORTS = (
    "alpha_algo_position_engine",
    "alpha_algo_pnl_engine",
    "alpha_algo_portfolio_engine",
)


def _sources():
    for path in PACKAGE_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path, path.read_text(encoding="utf-8")


def test_no_broker_specific_tokens_in_paper_core() -> None:
    for path, text in _sources():
        low = text.lower()
        for tok in FORBIDDEN_BROKER_TOKENS:
            assert tok not in low, f"{path.name} references broker-specific token {tok}"


def test_no_downstream_engine_bypass_in_paper_core() -> None:
    """Paper must route fills through boundaries, never mutate position/P&L/portfolio."""
    for path, text in _sources():
        for tok in FORBIDDEN_ENGINE_IMPORTS:
            assert tok not in text, f"{path.name} imports/mutates {tok}"


def test_no_live_enable_in_paper_core() -> None:
    for path, text in _sources():
        assert "LIVE_TRADING_ENABLED = true" not in text.lower(), path.name


def test_no_hardcoded_credential_secrets_in_paper_core() -> None:
    for path, text in _sources():
        for secret_hint in ("password =", "api_key =", "access_token =", "secret_key ="):
            assert secret_hint not in text.lower(), path.name


def test_paper_mode_never_routes_to_live() -> None:
    assert resolve_provider("PAPER").value == "PAPER"
    with pytest.raises(LiveTradingDisabledError):
        resolve_provider("LIVE")


def test_paper_broker_capabilities_never_live() -> None:
    adapter = PaperBrokerAdapter(clock=lambda: datetime.now(UTC), reference_prices={})
    assert adapter.capabilities.supports_live_trading is False
