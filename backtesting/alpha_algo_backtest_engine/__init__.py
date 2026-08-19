"""Backtest simulation engine (Phase 7, P7-002).

A pure, deterministic fill/cost/metrics simulator that composes the verified
P7-001 backtesting foundation. It consumes caller-decided order intents and
explicit historical inputs and produces an immutable :class:`BacktestRun`.
It takes no clock, reads no wall clock, performs no I/O, never generates
signals or UUIDs, and has no PAPER/LIVE/broker surface.

Fixed, auditable policy constants (breaking any of these is a contract
change, not an implementation detail — the ADR-0008 precedent):
``FILL_TIMING_POLICY``, ``TICK_MARKET_FILL_POLICY``, ``TICK_LIMIT_FILL_POLICY``,
``CANDLE_FILL_POLICY`` (+ ``CANDLE_LIMIT_NO_IMPROVEMENT``), ``SLIPPAGE_POLICY``,
``COMMISSION_POLICY``, ``EQUITY_MARK_POLICY``, ``COST_ATTRIBUTION_POLICY``.
"""

from __future__ import annotations

from alpha_algo_backtest_engine.costs import (
    COMMISSION_POLICY,
    CostModel,
    DECIMAL_PRECISION,
    SLIPPAGE_POLICY,
    apply_slippage,
    commission_for,
)
from alpha_algo_backtest_engine.engine import (
    EQUITY_MARK_POLICY,
    BacktestRun,
    EquityPoint,
    run_backtest,
)
from alpha_algo_backtest_engine.errors import BacktestEngineError, BacktestMetricsError
from alpha_algo_backtest_engine.fills import (
    CANDLE_FILL_POLICY,
    CANDLE_LIMIT_NO_IMPROVEMENT,
    FILL_TIMING_POLICY,
    FillOutcome,
    FillRecord,
    TICK_LIMIT_FILL_POLICY,
    TICK_MARKET_FILL_POLICY,
    UnfilledReason,
)
from alpha_algo_backtest_engine.intents import IntentSide, IntentType, OrderIntent
from alpha_algo_backtest_engine.ledger import COST_ATTRIBUTION_POLICY, TradeRecord
from alpha_algo_backtest_engine.metrics import BacktestMetrics, compute_metrics

__all__ = [
    "BacktestEngineError",
    "BacktestMetrics",
    "BacktestMetricsError",
    "BacktestRun",
    "CANDLE_FILL_POLICY",
    "CANDLE_LIMIT_NO_IMPROVEMENT",
    "COMMISSION_POLICY",
    "COST_ATTRIBUTION_POLICY",
    "CostModel",
    "DECIMAL_PRECISION",
    "EQUITY_MARK_POLICY",
    "EquityPoint",
    "FILL_TIMING_POLICY",
    "FillOutcome",
    "FillRecord",
    "IntentSide",
    "IntentType",
    "OrderIntent",
    "SLIPPAGE_POLICY",
    "TICK_LIMIT_FILL_POLICY",
    "TICK_MARKET_FILL_POLICY",
    "TradeRecord",
    "UnfilledReason",
    "apply_slippage",
    "commission_for",
    "compute_metrics",
    "run_backtest",
]
