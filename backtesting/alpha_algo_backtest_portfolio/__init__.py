"""Multi-symbol portfolio simulation for the backtesting subsystem (P16).

A deterministic, long-only, shared-capital portfolio simulator that composes
the existing single-instrument fill/cost/FIFO semantics across a symbol
universe with explicit capital allocation (reserved-cash floor + optional
per-symbol budget caps). No second production Portfolio/P&L engine is
created; simulation-specific accounting primitives reuse the engine's
formulas for consistency.

Safety boundaries: pure, deterministic, isolated from LIVE/PAPER and broker
APIs; long-only (short/flip rejected, matching the production Position
Engine).
"""

from alpha_algo_backtest_portfolio.capital import CAPITAL_ALLOCATION_POLICY, CapitalAllocation
from alpha_algo_backtest_portfolio.engine import (
    PORTFOLIO_EQUITY_MARK_POLICY,
    PORTFOLIO_FILL_TIMING_POLICY,
    PortfolioEquityPoint,
    PortfolioIntent,
    PortfolioResult,
    PortfolioTrade,
    run_portfolio_backtest,
)
from alpha_algo_backtest_portfolio.errors import PortfolioBacktestError
from alpha_algo_backtest_portfolio.inputs import PORTFOLIO_INPUT_POLICY, PortfolioInput

__all__ = [
    "CAPITAL_ALLOCATION_POLICY",
    "PORTFOLIO_EQUITY_MARK_POLICY",
    "PORTFOLIO_FILL_TIMING_POLICY",
    "PORTFOLIO_INPUT_POLICY",
    "CapitalAllocation",
    "PortfolioBacktestError",
    "PortfolioEquityPoint",
    "PortfolioInput",
    "PortfolioIntent",
    "PortfolioResult",
    "PortfolioTrade",
    "run_portfolio_backtest",
]
