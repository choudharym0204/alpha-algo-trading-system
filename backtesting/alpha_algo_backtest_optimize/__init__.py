"""Deterministic optimization and Monte Carlo for the backtesting subsystem (P16).

Additive research tooling: a reproducible lexicographic grid search (with
explicit train/test separation by caller-closure) and a seeded, deterministic
bootstrap Monte Carlo. No parallel execution, no shared mutable state, no
uncontrolled randomness.

Safety boundaries: pure functions, no network, no broker, no I/O, isolated
from LIVE/PAPER.
"""

from alpha_algo_backtest_optimize.errors import OptimizationError
from alpha_algo_backtest_optimize.grid import (
    GRID_SEARCH_POLICY,
    Evaluation,
    OptimizationResult,
    Parameter,
    ParameterGrid,
    ParameterPoint,
    evaluate_point,
    grid_search,
    select_best,
)
from alpha_algo_backtest_optimize.monte_carlo import (
    MONTE_CARLO_POLICY,
    MonteCarloSummary,
    bootstrap_paths,
    bootstrap_summary,
    deterministic_shuffle,
)

__all__ = [
    "GRID_SEARCH_POLICY",
    "MONTE_CARLO_POLICY",
    "Evaluation",
    "MonteCarloSummary",
    "OptimizationError",
    "OptimizationResult",
    "Parameter",
    "ParameterGrid",
    "ParameterPoint",
    "bootstrap_paths",
    "bootstrap_summary",
    "deterministic_shuffle",
    "evaluate_point",
    "grid_search",
    "select_best",
]
