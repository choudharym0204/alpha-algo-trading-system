from __future__ import annotations

"""Alpha Algo Paper Trading — deterministic PAPER-mode execution foundation.

This package implements the paper trading foundation (P8-001): a
PAPER-only simulator that produces simulator-confirmed fills from injected,
caller-owned reference prices, exposes them as execution-engine
``BrokerOrderEvent``\\ s, and keeps an append-only, idempotent paper book with
PAPER-labeled positions.

Scope boundary (see ADR-0007): this is the *foundation*, not the operational
paper trading feature. It contains no P&L, no slippage/commission models, no
market-data ingestion, no working orders, no persistence, no broker/network
access, and no way to select LIVE mode. ``PAPER_TRADING_VERIFIED`` (a LIVE
safety gate) remains TODO; LIVE remains disabled and unavailable.

The operational runtime (accounts, funds, runs, costs, mode routing, service,
persistence) lives in ``alpha_algo_paper_runtime`` (Phase 15).
"""

from alpha_algo_paper_trading.book import (
    ORDER_ID_NAMESPACE,
    PaperOrderBook,
    paper_order_id,
)
from alpha_algo_paper_trading.errors import (
    ClientOrderIdConflictError,
    PaperAdapterError,
    PaperMarketDataUnavailableError,
    PaperModeViolationError,
    UnsupportedOrderTypeError,
)
from alpha_algo_paper_trading.fill_policy import decide_fill
from alpha_algo_paper_trading.paper_broker import PaperBrokerAdapter
from alpha_algo_paper_trading.types import (
    AVERAGE_PRICE_QUANTUM,
    AVERAGE_PRICE_ROUNDING,
    FillDecision,
    PaperFillRecord,
    PaperPosition,
    PaperReferencePrice,
)

__all__ = [
    "AVERAGE_PRICE_QUANTUM",
    "AVERAGE_PRICE_ROUNDING",
    "ClientOrderIdConflictError",
    "FillDecision",
    "ORDER_ID_NAMESPACE",
    "PaperAdapterError",
    "PaperBrokerAdapter",
    "PaperFillRecord",
    "PaperMarketDataUnavailableError",
    "PaperModeViolationError",
    "PaperOrderBook",
    "PaperPosition",
    "PaperReferencePrice",
    "UnsupportedOrderTypeError",
    "decide_fill",
    "paper_order_id",
]
