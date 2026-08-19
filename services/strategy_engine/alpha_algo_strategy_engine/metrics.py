"""In-process strategy-runtime metrics (observability, thread-safe)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyMetrics:
    strategies_started: int = 0
    strategies_stopped: int = 0
    strategies_paused: int = 0
    strategies_resumed: int = 0
    strategies_failed: int = 0

    events_dispatched: int = 0
    events_dropped: int = 0
    callback_count: int = 0
    callback_latency_seconds_total: float = 0.0
    event_lag_seconds_total: float = 0.0

    signals_generated: int = 0
    signals_rejected: int = 0
    signals_duplicate: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def active_strategies(self) -> int:
        return self.strategies_started - self.strategies_stopped

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def record_callback(self, latency_seconds: float) -> None:
        with self._lock:
            self.callback_count += 1
            self.callback_latency_seconds_total += latency_seconds

    def record_event_lag(self, lag_seconds: float) -> None:
        with self._lock:
            self.event_lag_seconds_total += lag_seconds

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                **{k: v for k, v in self.__dict__.items() if not k.startswith("_")},
                "active_strategies": self.active_strategies,
            }
