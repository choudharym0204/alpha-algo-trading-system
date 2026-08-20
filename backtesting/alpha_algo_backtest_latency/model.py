"""Deterministic latency modeling for the backtesting subsystem (P16).

Latency shifts the **effective decision time** of an order intent by a
deterministic, configurable delay. Because the engine anchors an intent at
the first record strictly after its ``decided_at``, advancing ``decided_at``
by the latency moves the fill later in the replayed history — latency is
controlled by simulation time, never by wall-clock sleep.

Components (each a non-negative ``timedelta``, all zero by default):

- ``signal_latency`` — signal generation to order decision.
- ``decision_latency`` — decision to order submission.
- ``submission_latency`` — submission to fill availability.
- ``fill_latency`` — fill availability to fill confirmation.

The effective decision time is ``decided_at + total_latency``. The model is
pure and deterministic; it performs no sleeping and reads no wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

from alpha_algo_backtest_engine import OrderIntent

from alpha_algo_backtest_latency.errors import LatencyError

__all__ = ["LATENCY_POLICY", "LatencyModel", "apply_latency", "apply_latency_to_intent"]

LATENCY_POLICY = (
    "Latency shifts effective decision time by a deterministic sum of "
    "component delays (signal/decision/submission/fill, all non-negative, "
    "zero by default). No wall-clock sleep; simulation time controls latency. "
    "Included in backtest identity by the caller (config/seed)."
)


@dataclass(frozen=True)
class LatencyModel:
    """Deterministic latency components for one simulation configuration."""

    signal_latency: timedelta = timedelta(0)
    decision_latency: timedelta = timedelta(0)
    submission_latency: timedelta = timedelta(0)
    fill_latency: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        for name, value in (
            ("signal_latency", self.signal_latency),
            ("decision_latency", self.decision_latency),
            ("submission_latency", self.submission_latency),
            ("fill_latency", self.fill_latency),
        ):
            if not isinstance(value, timedelta):
                raise LatencyError(f"{name} must be a timedelta")
            if value < timedelta(0):
                raise LatencyError(f"{name} must be non-negative")

    @property
    def total_latency(self) -> timedelta:
        return self.signal_latency + self.decision_latency + self.submission_latency + self.fill_latency

    @property
    def is_zero(self) -> bool:
        return self.total_latency == timedelta(0)


def apply_latency_to_intent(intent: OrderIntent, model: LatencyModel) -> OrderIntent:
    """Return a new intent with ``decided_at`` advanced by the total latency."""
    if not isinstance(intent, OrderIntent):
        raise LatencyError("intent must be an OrderIntent")
    if not isinstance(model, LatencyModel):
        raise LatencyError("model must be a LatencyModel")
    return replace(intent, decided_at=intent.decided_at + model.total_latency)


def apply_latency(intents: tuple[OrderIntent, ...], model: LatencyModel) -> tuple[OrderIntent, ...]:
    """Shift the effective decision time of every intent (pure, deterministic)."""
    if not isinstance(intents, tuple) or not all(isinstance(i, OrderIntent) for i in intents):
        raise LatencyError("intents must be a tuple of OrderIntent")
    if not isinstance(model, LatencyModel):
        raise LatencyError("model must be a LatencyModel")
    return tuple(apply_latency_to_intent(intent, model) for intent in intents)
