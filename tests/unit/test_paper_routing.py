from __future__ import annotations

import pytest

from alpha_algo_paper_runtime import (
    ExecutionProvider,
    LiveTradingDisabledError,
    TradingHaltedError,
    TradingModeRouter,
    UnknownTradingModeError,
    resolve_provider,
)


def test_resolve_paper() -> None:
    assert resolve_provider("PAPER") is ExecutionProvider.PAPER


def test_resolve_backtest() -> None:
    assert resolve_provider("BACKTEST") is ExecutionProvider.BACKTEST


def test_resolve_live_is_blocked() -> None:
    with pytest.raises(LiveTradingDisabledError, match="LIVE"):
        resolve_provider("LIVE")


def test_resolve_live_case_insensitive_blocked() -> None:
    with pytest.raises(LiveTradingDisabledError, match="LIVE"):
        resolve_provider("live")


def test_resolve_unknown_mode_fails() -> None:
    with pytest.raises(UnknownTradingModeError, match="unknown"):
        resolve_provider("SANDBOX")


def test_resolve_missing_mode_fails() -> None:
    with pytest.raises(UnknownTradingModeError):
        resolve_provider(None)


def test_router_halt_blocks_everything() -> None:
    router = TradingModeRouter(global_halt_active=lambda: True)
    with pytest.raises(TradingHaltedError, match="halt"):
        router.resolve("PAPER")


def test_router_live_enabled_still_blocks_live() -> None:
    router = TradingModeRouter(
        live_trading_enabled=lambda: True, global_halt_active=lambda: False
    )
    with pytest.raises(LiveTradingDisabledError):
        router.resolve("LIVE")


def test_router_paper_never_selects_live() -> None:
    router = TradingModeRouter()
    assert router.paper_never_selects_live() is True


def test_router_resolves_paper_when_clear() -> None:
    router = TradingModeRouter(global_halt_active=lambda: False, live_trading_enabled=lambda: False)
    assert router.resolve("PAPER") is ExecutionProvider.PAPER
