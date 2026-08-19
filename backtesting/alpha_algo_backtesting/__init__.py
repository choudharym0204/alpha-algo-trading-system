"""Deterministic backtesting foundation (Phase 7, P7-001).

This package is the BACKTEST-mode foundation of the Alpha Algo Trading
System. It provides a deterministic simulation clock, strict explicit
historical input validation, a replay cursor, and an audit-producing
session — and nothing else.

Safety boundaries (non-negotiable):

- BACKTEST is structurally isolated from PAPER and LIVE modes.
- Only explicit historical inputs are accepted; no sample data is embedded.
- No broker credentials, no network access, no environment-variable reads.
- No fills, orders, positions, P&L, slippage, or commission logic.
- LIVE trading is never enabled from this package.
"""

from alpha_algo_backtesting.clock import SimulationClock
from alpha_algo_backtesting.hashing import (
    CANONICAL_SERIALIZER_VERSION,
    MANIFEST_SCHEMA_VERSION,
    canonical_bytes,
    canonical_serialize,
    content_sha256,
)
from alpha_algo_backtesting.input_data import BacktestInput
from alpha_algo_backtesting.mode import BacktestTradingMode
from alpha_algo_backtesting.replay import DataReplayCursor
from alpha_algo_backtesting.session import BacktestAuditRecord, BacktestSession, InputManifest

__all__ = [
    "BacktestAuditRecord",
    "BacktestInput",
    "BacktestSession",
    "BacktestTradingMode",
    "CANONICAL_SERIALIZER_VERSION",
    "DataReplayCursor",
    "InputManifest",
    "MANIFEST_SCHEMA_VERSION",
    "SimulationClock",
    "canonical_bytes",
    "canonical_serialize",
    "content_sha256",
]
