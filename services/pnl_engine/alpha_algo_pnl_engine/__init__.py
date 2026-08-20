"""Alpha Algo P&L Engine (Phase 13).

Deterministic, auditable, broker-independent realized + unrealized P&L derived
from authoritative execution/position facts (Phase 11) and normalized reference
prices (Phase 3/12). Weighted-average cost (long-only). No reconciliation
(Phase 14), no broker calls, LIVE fail-closed.
"""

from alpha_algo_pnl_engine.accounting import (
    MONEY_QUANTUM,
    costs_total,
    net_pnl,
    realized_pnl_long,
    round_money,
    unrealized_pnl_long,
)
from alpha_algo_pnl_engine.aggregation import (
    account_aggregation,
    aggregate_realized,
    combine_unrealized,
    daily_aggregation,
    strategy_aggregation,
)
from alpha_algo_pnl_engine.contracts import (
    AggregatedPnl,
    CostComponent,
    PnlApplyStatus,
    PnlEvent,
    PnlEventType,
    PnlResult,
    PnlSnapshot,
    PnlStatus,
    PositionPnl,
    PriceState,
    RealizedPnl,
    UnrealizedPnl,
)
from alpha_algo_pnl_engine.engine import PnlEngine, PnlRepository
from alpha_algo_pnl_engine.errors import (
    DuplicateExecutionError,
    PnlConflictError,
    PnlDataError,
    PnlError,
    PnlModeError,
    PnlOverCloseError,
    PnlPersistenceError,
    PnlRejectedError,
    PnlValidationError,
)
from alpha_algo_pnl_engine.identity import compute_snapshot_key, event_content_hash
from alpha_algo_pnl_engine.metrics import PnlMetrics
from alpha_algo_pnl_engine.unrealized import classify_price, mark_to_market

__all__ = [
    "MONEY_QUANTUM",
    "AggregatedPnl",
    "CostComponent",
    "DuplicateExecutionError",
    "PnlApplyStatus",
    "PnlConflictError",
    "PnlDataError",
    "PnlEngine",
    "PnlError",
    "PnlEvent",
    "PnlEventType",
    "PnlMetrics",
    "PnlModeError",
    "PnlOverCloseError",
    "PnlPersistenceError",
    "PnlRejectedError",
    "PnlRepository",
    "PnlResult",
    "PnlSnapshot",
    "PnlStatus",
    "PnlValidationError",
    "PositionPnl",
    "PriceState",
    "RealizedPnl",
    "UnrealizedPnl",
    "account_aggregation",
    "aggregate_realized",
    "classify_price",
    "combine_unrealized",
    "compute_snapshot_key",
    "costs_total",
    "daily_aggregation",
    "event_content_hash",
    "mark_to_market",
    "net_pnl",
    "realized_pnl_long",
    "round_money",
    "strategy_aggregation",
    "unrealized_pnl_long",
]
