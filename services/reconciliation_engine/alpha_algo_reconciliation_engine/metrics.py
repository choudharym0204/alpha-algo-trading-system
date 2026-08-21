"""Reconciliation Engine observability metrics (Phase 14)."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_algo_reconciliation_engine.contracts import RunStatus


@dataclass
class ReconciliationMetrics:
    runs: int = 0
    completed_runs: int = 0
    partial_runs: int = 0
    failed_runs: int = 0
    matched_entities: int = 0
    mismatched_entities: int = 0
    unknown_entities: int = 0
    conflicts: int = 0
    open_discrepancies: int = 0

    def record_run(self, status: RunStatus) -> None:
        self.runs += 1
        if status == RunStatus.COMPLETED:
            self.completed_runs += 1
        elif status == RunStatus.PARTIAL:
            self.partial_runs += 1
        elif status == RunStatus.FAILED:
            self.failed_runs += 1

    def record_match(self, n: int = 1) -> None:
        self.matched_entities += n

    def record_mismatch(self, n: int = 1) -> None:
        self.mismatched_entities += n

    def record_unknown(self, n: int = 1) -> None:
        self.unknown_entities += n

    def record_conflict(self) -> None:
        self.conflicts += 1
