"""Deterministic latency modeling for the backtesting subsystem (P16).

Configurable, deterministic latency that shifts order-intent effective
decision time. Simulation time controls latency; no wall-clock sleep, no
randomness, no network.

Safety boundaries: pure functions, isolated from LIVE/PAPER and broker APIs.
"""

from alpha_algo_backtest_latency.errors import LatencyError
from alpha_algo_backtest_latency.model import (
    LATENCY_POLICY,
    LatencyModel,
    apply_latency,
    apply_latency_to_intent,
)

__all__ = [
    "LATENCY_POLICY",
    "LatencyError",
    "LatencyModel",
    "apply_latency",
    "apply_latency_to_intent",
]
