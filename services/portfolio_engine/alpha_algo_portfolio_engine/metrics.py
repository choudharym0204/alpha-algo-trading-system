"""Portfolio Engine observability metrics (Phase 12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class PortfolioMetrics:
    recalculations: int = 0
    snapshot_writes: int = 0
    snapshot_failures: int = 0
    stale_snapshots: int = 0
    incomplete_snapshots: int = 0
    duplicate_snapshots: int = 0
    recalculation_latency_us: float = 0.0
    _clock: Callable[[], float] = field(
        default_factory=lambda: perf_counter, repr=False
    )

    def record_recalculation(self) -> None:
        self.recalculations += 1

    def record_snapshot_write(self) -> None:
        self.snapshot_writes += 1

    def record_snapshot_failure(self) -> None:
        self.snapshot_failures += 1

    def record_stale(self) -> None:
        self.stale_snapshots += 1

    def record_incomplete(self) -> None:
        self.incomplete_snapshots += 1

    def record_duplicate(self) -> None:
        self.duplicate_snapshots += 1

    def record_latency(self, seconds: float) -> None:
        self.recalculation_latency_us += seconds * 1_000_000
