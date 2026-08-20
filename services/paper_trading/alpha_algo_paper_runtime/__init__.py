from __future__ import annotations

"""Alpha Algo Paper Runtime (Phase 15) — the operational paper trading layer.

Builds the complete paper lifecycle on top of the deterministic
``alpha_algo_paper_trading`` foundation: an explicit PAPER account model, a
cash/reserve funds ledger, paper-run identity, a deterministic cost model
(slippage + commission), an authoritative trading-mode routing boundary (LIVE
fail-closed), the ``PaperTradingService`` orchestrator, and the persistence
boundary.

LIVE remains disabled and fail-closed everywhere; paper results are simulated
and PAPER-labeled.
"""

from alpha_algo_paper_runtime.account import PaperAccount, PaperAccountStatus
from alpha_algo_paper_runtime.costs import (
    CommissionModel,
    PaperCostModel,
    SlippageModel,
    apply_slippage,
    commission_amount,
)
from alpha_algo_paper_runtime.funds import PaperFunds
from alpha_algo_paper_runtime.repository import PaperRepository, SqlPaperRepository
from alpha_algo_paper_runtime.routing import (
    ExecutionProvider,
    LiveTradingDisabledError,
    TradingHaltedError,
    TradingModeRouter,
    UnknownTradingModeError,
    resolve_provider,
)
from alpha_algo_paper_runtime.run import (
    PAPER_RUN_NAMESPACE,
    PaperRun,
    PaperRunStatus,
    compute_config_hash,
    new_paper_run_id,
)
from alpha_algo_paper_runtime.service import PaperFillOutcome, PaperTradingService

__all__ = [
    "CommissionModel",
    "ExecutionProvider",
    "LiveTradingDisabledError",
    "PAPER_RUN_NAMESPACE",
    "PaperAccount",
    "PaperAccountStatus",
    "PaperCostModel",
    "PaperFillOutcome",
    "PaperFunds",
    "PaperRepository",
    "PaperRun",
    "PaperRunStatus",
    "PaperTradingService",
    "SlippageModel",
    "SqlPaperRepository",
    "TradingHaltedError",
    "TradingModeRouter",
    "UnknownTradingModeError",
    "apply_slippage",
    "commission_amount",
    "compute_config_hash",
    "new_paper_run_id",
    "resolve_provider",
]
