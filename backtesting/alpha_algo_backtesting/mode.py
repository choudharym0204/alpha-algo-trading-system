from __future__ import annotations

from enum import StrEnum


class BacktestTradingMode(StrEnum):
    """Trading mode for a backtesting session.

    This enum deliberately has exactly one member. BACKTEST mode is
    structurally isolated from PAPER and LIVE modes: there is no value in
    this enum that could select a paper or live trading path, so mode
    leakage is a type error rather than a runtime mistake.

    Live trading must never be enabled from a backtesting foundation.
    """

    BACKTEST = "BACKTEST"
