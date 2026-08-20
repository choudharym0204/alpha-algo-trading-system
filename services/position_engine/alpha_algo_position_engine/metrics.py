"""Position Engine observability metrics (Phase 11).

Counter-based in-process metrics (no external agent, no secrets). Correlation
fields (execution id, order id, position id, account, instrument) are attached
per-increment for traceability. Credentials are never logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class PositionMetrics:
    positions_opened: int = 0
    positions_increased: int = 0
    positions_decreased: int = 0
    positions_closed: int = 0
    positions_flipped: int = 0
    duplicate_fills: int = 0
    conflicting_fills: int = 0
    rejected_fills: int = 0
    concurrency_conflicts: int = 0
    transaction_failures: int = 0
    calculation_latency_us: float = 0.0
    _clock: Callable[[], float] = field(
        default_factory=lambda: perf_counter, repr=False
    )

    def record_opened(self) -> None:
        self.positions_opened += 1

    def record_increased(self) -> None:
        self.positions_increased += 1

    def record_decreased(self) -> None:
        self.positions_decreased += 1

    def record_closed(self) -> None:
        self.positions_closed += 1

    def record_flip(self) -> None:
        self.positions_flipped += 1

    def record_duplicate(self) -> None:
        self.duplicate_fills += 1

    def record_conflict(self) -> None:
        self.conflicting_fills += 1

    def record_rejection(self) -> None:
        self.rejected_fills += 1

    def record_concurrency_conflict(self) -> None:
        self.concurrency_conflicts += 1

    def record_transaction_failure(self) -> None:
        self.transaction_failures += 1

    def record_latency(self, seconds: float) -> None:
        self.calculation_latency_us += seconds * 1_000_000

    @property
    def active_position_count_hint(self) -> int:
        """Net activity: (opened + increased) - (decreased + closed)."""
        return (
            self.positions_opened
            + self.positions_increased
            - self.positions_decreased
            - self.positions_closed
        )

    @property
    def position_event_count(self) -> int:
        return (
            self.positions_opened
            + self.positions_increased
            + self.positions_decreased
            + self.positions_closed
            + self.conflicting_fills
        )
