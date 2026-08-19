"""Signal-engine observability metrics (thread-safe counters)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalMetrics:
    signals_received: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    signals_duplicate: int = 0
    signals_conflict: int = 0
    signals_expired: int = 0
    signals_persisted: int = 0
    persistence_failures: int = 0
    processing_latency_seconds_total: float = 0.0

    per_strategy: dict[str, int] = field(default_factory=dict)
    per_instrument: dict[str, int] = field(default_factory=dict)

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def record_latency(self, latency_seconds: float) -> None:
        with self._lock:
            self.processing_latency_seconds_total += latency_seconds

    def record_key(self, name: str, key: str) -> None:
        with self._lock:
            bucket = getattr(self, name)
            bucket[key] = bucket.get(key, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
