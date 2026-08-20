"""Execution submission state + attempt record (Phase 9).

The submission lifecycle is the Execution Engine's *internal* tracking of a
submission attempt — distinct from the OMS `OrderLifecycle` (which the engine
drives through trusted events). A timeout does NOT mean REJECTED: it means the
external state is ambiguous (UNKNOWN), because the provider may have accepted
the order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ExecutionSubmissionState(StrEnum):
    SUBMISSION_REQUESTED = "SUBMISSION_REQUESTED"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ExecutionAttempt:
    """An immutable snapshot of one submission attempt."""

    attempt_id: str
    execution_id: str
    order_id: UUID
    attempt_number: int
    state: ExecutionSubmissionState
    broker_order_id: str | None = None
    submitted_at: datetime | None = None
    responded_at: datetime | None = None
    reason: str = ""
