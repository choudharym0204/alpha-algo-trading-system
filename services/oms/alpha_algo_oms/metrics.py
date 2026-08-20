"""OMS observability metrics (Phase 8).

Counter-based metrics (no external agent, no secrets). Correlation fields
(orchestration id, order id, signal id, risk approval id, account, instrument)
are attached per-increment for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class OmsMetrics:
    """In-process counters for OMS operations."""

    orders_created: int = 0
    duplicate_intents: int = 0
    duplicate_orders: int = 0
    conflicts: int = 0
    rejections: int = 0
    state_transitions: int = 0
    cancellation_requests: int = 0
    unknown_states: int = 0
    reconciliation_required: int = 0
    persistence_failures: int = 0
    _clock: Callable[[], float] = field(
        default_factory=lambda: perf_counter, repr=False
    )

    def record_created(self) -> None:
        self.orders_created += 1

    def record_duplicate_intent(self) -> None:
        self.duplicate_intents += 1

    def record_duplicate_order(self) -> None:
        self.duplicate_orders += 1

    def record_conflict(self) -> None:
        self.conflicts += 1

    def record_rejection(self) -> None:
        self.rejections += 1

    def record_transition(self) -> None:
        self.state_transitions += 1

    def record_cancellation_request(self) -> None:
        self.cancellation_requests += 1

    def record_unknown(self) -> None:
        self.unknown_states += 1

    def record_reconciliation_required(self) -> None:
        self.reconciliation_required += 1

    def record_persistence_failure(self) -> None:
        self.persistence_failures += 1
