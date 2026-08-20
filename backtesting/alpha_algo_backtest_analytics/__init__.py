"""Advanced performance analytics for the backtesting subsystem (Phase 16).

Additive analytics over the deterministic backtesting engine: CAGR
(annualized return), historical VaR/CVaR, CAPM-style Alpha/Beta against an
aligned benchmark, and per-trade MFE/MAE excursions.

Safety boundaries (non-negotiable):

- Pure, deterministic functions of explicit inputs — no wall clock, no
  randomness, no network, no broker, no I/O.
- Isolated from LIVE/PAPER; nothing here can place an order or enable live
  trading.
- Every metric is a hypothetical reconstruction of the explicit historical
  inputs; none is evidence of profitability or forward performance.
- Undefined metrics are ``None``; contract violations raise typed errors.
"""

from alpha_algo_backtest_analytics.advanced import (
    ADVANCED_METRICS_POLICY,
    AdvancedMetrics,
    compute_advanced_metrics,
)
from alpha_algo_backtest_analytics.alpha_beta import (
    ALPHA_BETA_POLICY,
    AlphaBetaMetrics,
    compute_alpha_beta,
)
from alpha_algo_backtest_analytics.cagr import CAGR_POLICY, CagrResult, compute_cagr
from alpha_algo_backtest_analytics.errors import (
    AnalyticsError,
    AnnualizationError,
    ExcursionError,
    RiskMeasureError,
)
from alpha_algo_backtest_analytics.excursions import (
    EXCURSION_POLICY,
    ExcursionPoint,
    ExcursionResult,
    ExcursionSide,
    compute_excursions,
)
from alpha_algo_backtest_analytics.var import (
    HISTORICAL_VAR_POLICY,
    VarCvarMetrics,
    compute_var_cvar,
)

__all__ = [
    "ADVANCED_METRICS_POLICY",
    "ALPHA_BETA_POLICY",
    "AdvancedMetrics",
    "AlphaBetaMetrics",
    "AnalyticsError",
    "AnnualizationError",
    "CAGR_POLICY",
    "CagrResult",
    "EXCURSION_POLICY",
    "ExcursionError",
    "ExcursionPoint",
    "ExcursionResult",
    "ExcursionSide",
    "HISTORICAL_VAR_POLICY",
    "RiskMeasureError",
    "VarCvarMetrics",
    "compute_advanced_metrics",
    "compute_alpha_beta",
    "compute_cagr",
    "compute_excursions",
    "compute_var_cvar",
]
