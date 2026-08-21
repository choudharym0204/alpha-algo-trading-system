"""In-process market-data metrics (observability).

Simple counters — no external monitoring dependency. The engine increments these
and periodically logs a summary; the counters are also the assertions used by
tests. Redis/Prometheus wiring is intentionally out of scope (no premature infra).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarketDataMetrics:
    connected: int = 0
    disconnected: int = 0
    connect_failures: int = 0
    reconnects: int = 0
    reconnect_failures: int = 0
    heartbeat_failures: int = 0
    ticks_received: int = 0
    candles_received: int = 0
    duplicates: int = 0
    stale_events: int = 0
    future_timestamps: int = 0
    rejected_events: int = 0
    normalization_failures: int = 0
    dropped_events: int = 0
    persisted_ticks: int = 0
    persisted_candles: int = 0
    persistence_failures: int = 0
    consumer_failures: int = 0
    provider_latency_seconds_total: float = 0.0

    def record_tick(self) -> None:
        self.ticks_received += 1

    def record_candle(self) -> None:
        self.candles_received += 1

    def record_latency(self, seconds: float) -> None:
        self.provider_latency_seconds_total += seconds

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
