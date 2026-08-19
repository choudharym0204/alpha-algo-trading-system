"""Trading orchestration lifecycle state machine (Phase 7).

The orchestrator coordinates Phase-5 signal acceptance → Phase-6 risk → a
durable, OMS-ready intent. It never performs the business logic itself; the
state machine only records the deterministic, auditable progression of a single
signal through the coordination boundary.
"""

from __future__ import annotations

from enum import StrEnum


class OrchestrationState(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    RISK_EVALUATED = "risk_evaluated"
    APPROVED = "approved"
    OMS_HANDOFF_READY = "oms_handoff_ready"
    REJECTED = "rejected"
    FAILED = "failed"
    DUPLICATE = "duplicate"


TERMINAL_STATES = frozenset(
    {
        OrchestrationState.REJECTED,
        OrchestrationState.FAILED,
        OrchestrationState.DUPLICATE,
        OrchestrationState.OMS_HANDOFF_READY,
    }
)

# Allowed transitions (deterministic; terminal states have no outgoing edges).
_TRANSITIONS: dict[OrchestrationState, frozenset[OrchestrationState]] = {
    OrchestrationState.RECEIVED: frozenset(
        {OrchestrationState.VALIDATED, OrchestrationState.REJECTED}
    ),
    OrchestrationState.VALIDATED: frozenset(
        {OrchestrationState.RISK_EVALUATED, OrchestrationState.REJECTED}
    ),
    OrchestrationState.RISK_EVALUATED: frozenset(
        {OrchestrationState.APPROVED, OrchestrationState.REJECTED}
    ),
    OrchestrationState.APPROVED: frozenset(
        {OrchestrationState.OMS_HANDOFF_READY, OrchestrationState.FAILED}
    ),
}


class OrchestrationStateError(Exception):
    """Raised on an illegal orchestration state transition."""


class OrchestrationStateMachine:
    def __init__(self) -> None:
        self._state = OrchestrationState.RECEIVED

    @property
    def state(self) -> OrchestrationState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def transition(self, to: OrchestrationState) -> OrchestrationState:
        allowed = _TRANSITIONS.get(self._state)
        if allowed is None or to not in allowed:
            raise OrchestrationStateError(
                f"illegal transition {self._state.value} -> {to.value}"
            )
        self._state = to
        return to
