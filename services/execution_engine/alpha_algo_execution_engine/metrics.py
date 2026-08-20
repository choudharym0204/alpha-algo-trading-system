"""Execution-engine observability metrics (Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class ExecutionMetrics:
    """In-process counters for execution operations."""

    requests: int = 0
    submissions: int = 0
    acknowledgments: int = 0
    rejects: int = 0
    timeouts: int = 0
    retries: int = 0
    cancellations: int = 0
    fills: int = 0
    partial_fills: int = 0
    duplicate_events: int = 0
    duplicate_requests: int = 0
    unknown_states: int = 0
    failures: int = 0
    validation_rejections: int = 0
    _clock: Callable[[], float] = field(
        default_factory=lambda: perf_counter, repr=False
    )

    def record_request(self) -> None:
        self.requests += 1

    def record_submission(self) -> None:
        self.submissions += 1

    def record_acknowledgment(self) -> None:
        self.acknowledgments += 1

    def record_reject(self) -> None:
        self.rejects += 1

    def record_timeout(self) -> None:
        self.timeouts += 1

    def record_retry(self) -> None:
        self.retries += 1

    def record_cancellation(self) -> None:
        self.cancellations += 1

    def record_fill(self) -> None:
        self.fills += 1

    def record_partial_fill(self) -> None:
        self.partial_fills += 1

    def record_duplicate_event(self) -> None:
        self.duplicate_events += 1

    def record_duplicate_request(self) -> None:
        self.duplicate_requests += 1

    def record_unknown(self) -> None:
        self.unknown_states += 1

    def record_failure(self) -> None:
        self.failures += 1

    def record_validation_rejection(self) -> None:
        self.validation_rejections += 1
