from __future__ import annotations

"""Trading-mode routing boundary (Phase 15).

Explicit, authoritative mode routing — never driven by UI strings:

    BACKTEST -> backtest engine
    PAPER    -> paper broker
    LIVE     -> blocked (fail-closed, future controlled release only)

LIVE and unknown/missing modes fail loud. A PAPER configuration can never load
a live adapter, and the global halt gates everything.
"""

from enum import StrEnum
from typing import Callable


class ExecutionProvider(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class UnknownTradingModeError(ValueError):
    """Raised for a missing or unrecognized trading mode."""


class LiveTradingDisabledError(ValueError):
    """Raised whenever LIVE would be selected. Fail-closed: never routable."""


class TradingHaltedError(ValueError):
    """Raised when the global trading halt is active."""


def resolve_provider(trading_mode: str | None) -> ExecutionProvider:
    """Pure mode -> provider resolution. LIVE is never a valid result."""
    mode = (trading_mode or "").upper()
    if mode == "LIVE":
        raise LiveTradingDisabledError("LIVE trading is disabled (fail-closed)")
    if mode == "PAPER":
        return ExecutionProvider.PAPER
    if mode == "BACKTEST":
        return ExecutionProvider.BACKTEST
    raise UnknownTradingModeError(f"unknown trading mode: {trading_mode!r}")


class TradingModeRouter:
    """Authoritative routing boundary with injected safety hooks.

    ``live_trading_enabled`` defaults to ``False`` and ``global_halt_active``
    defaults to ``True`` (fail-closed), matching the platform defaults.
    """

    def __init__(
        self,
        *,
        live_trading_enabled: Callable[[], bool] | None = None,
        global_halt_active: Callable[[], bool] | None = None,
    ) -> None:
        self._live_enabled = live_trading_enabled or (lambda: False)
        self._halt_active = global_halt_active or (lambda: True)

    def resolve(self, trading_mode: str | None) -> ExecutionProvider:
        """Resolve a mode to its provider, enforcing halt + LIVE fail-closed."""
        if self._halt_active():
            raise TradingHaltedError("global trading halt is active")
        if self._live_enabled():
            raise LiveTradingDisabledError(
                "LIVE trading cannot be routed while live_trading_enabled is true"
            )
        return resolve_provider(trading_mode)

    def paper_never_selects_live(self) -> bool:
        """Structural guarantee: PAPER resolves to PAPER, LIVE is unreachable."""
        return resolve_provider("PAPER") is ExecutionProvider.PAPER
