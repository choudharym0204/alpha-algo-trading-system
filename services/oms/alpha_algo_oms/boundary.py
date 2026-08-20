"""Execution boundary (Phase 8).

The OMS stops at SUBMISSION_REQUESTED. The ``ExecutionPort`` is the explicit
handoff point to the future Phase-9 Execution Engine; it is NOT a broker and
never dispatches an order. ``NoOpExecutionPort`` is the default (accepts the
handoff without side effects). The OMS must never cross this boundary itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from alpha_algo_execution_engine.submission import BrokerSubmissionIntent


@dataclass(frozen=True)
class SubmissionHandoff:
    """The payload handed to the execution boundary at SUBMISSION_REQUESTED."""

    order_id: UUID
    broker_submission_intent: BrokerSubmissionIntent


class ExecutionPort(Protocol):
    """Receives orders that have reached SUBMISSION_REQUESTED (Phase 9 owns it)."""

    def submit(self, handoff: SubmissionHandoff) -> None: ...


class NoOpExecutionPort:
    """Default boundary: records the handoff without performing execution."""

    def submit(self, handoff: SubmissionHandoff) -> None:
        return None


class ExecutionBoundary:
    """Guards the OMS/execution seam so the OMS never dispatches to a broker."""

    def __init__(self, port: ExecutionPort | None = None) -> None:
        self._port = port or NoOpExecutionPort()

    def submit(self, handoff: SubmissionHandoff) -> None:
        """Forward a submission-ready order to the execution port (Phase 9)."""
        self._port.submit(handoff)
