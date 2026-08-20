"""P&L Engine observability metrics (Phase 13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class PnlMetrics:
    realized_events: int = 0
    unrealized_calculations: int = 0
    cost_applications: int = 0
    conflicts: int = 0
    duplicates: int = 0
    rejections: int = 0
    stale_price_calculations: int = 0
    unavailable_price_calculations: int = 0
    snapshot_writes: int = 0
    calculation_latency_us: float = 0.0
    _clock: Callable[[], float] = field(default_factory=lambda: perf_counter, repr=False)

    def record_realized(self) -> None:
        self.realized_events += 1

    def record_unrealized(self) -> None:
        self.unrealized_calculations += 1

    def record_cost(self) -> None:
        self.cost_applications += 1

    def record_conflict(self) -> None:
        self.conflicts += 1

    def record_duplicate(self) -> None:
        self.duplicates += 1

    def record_rejection(self) -> None:
        self.rejections += 1

    def record_stale(self) -> None:
        self.stale_price_calculations += 1

    def record_unavailable(self) -> None:
        self.unavailable_price_calculations += 1

    def record_snapshot_write(self) -> None:
        self.snapshot_writes += 1

    def record_latency(self, seconds: float) -> None:
        self.calculation_latency_us += seconds * 1_000_000
