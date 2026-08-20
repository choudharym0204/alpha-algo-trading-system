"""Alpha Algo Portfolio Engine (Phase 12).

Broker-independent, deterministic, durable portfolio aggregation over
authoritative position + funds + reference-price state. Account- and
mode-isolated; no P&L (Phase 13), no reconciliation (Phase 14), LIVE fail-closed.
"""

from alpha_algo_portfolio_engine.aggregation import (
    MONEY_QUANTUM,
    aggregate_positions,
    classify_price,
    compute_portfolio,
    round_money,
    strategy_breakdown,
)
from alpha_algo_portfolio_engine.contracts import (
    FundsState,
    PortfolioCompleteness,
    PortfolioComputation,
    PortfolioIdentity,
    PortfolioInputs,
    PortfolioResult,
    PortfolioSnapshot,
    PortfolioStatus,
    PositionExposure,
    PositionInput,
    ReferencePrice,
    StrategyBreakdown,
)
from alpha_algo_portfolio_engine.engine import (
    PortfolioEngine,
    PortfolioRepository,
)
from alpha_algo_portfolio_engine.errors import (
    DuplicateSnapshotError,
    PortfolioDataError,
    PortfolioError,
    PortfolioIdentityError,
    PortfolioModeError,
    PortfolioPersistenceError,
    PortfolioValidationError,
)
from alpha_algo_portfolio_engine.identity import (
    build_portfolio_identity,
    compute_portfolio_key,
    compute_snapshot_key,
    snapshot_content_hash,
)
from alpha_algo_portfolio_engine.metrics import PortfolioMetrics

__all__ = [
    "MONEY_QUANTUM",
    "DuplicateSnapshotError",
    "FundsState",
    "PortfolioCompleteness",
    "PortfolioComputation",
    "PortfolioDataError",
    "PortfolioEngine",
    "PortfolioError",
    "PortfolioIdentity",
    "PortfolioIdentityError",
    "PortfolioInputs",
    "PortfolioMetrics",
    "PortfolioModeError",
    "PortfolioPersistenceError",
    "PortfolioRepository",
    "PortfolioResult",
    "PortfolioSnapshot",
    "PortfolioStatus",
    "PortfolioValidationError",
    "PositionExposure",
    "PositionInput",
    "ReferencePrice",
    "StrategyBreakdown",
    "aggregate_positions",
    "build_portfolio_identity",
    "classify_price",
    "compute_portfolio",
    "compute_portfolio_key",
    "compute_snapshot_key",
    "round_money",
    "snapshot_content_hash",
    "strategy_breakdown",
]
