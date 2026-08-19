"""Signal lifecycle state machine (deterministic, auditable, transition-safe)."""

from __future__ import annotations

from enum import StrEnum


class SignalState(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    PERSISTED = "persisted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    EXPIRED = "expired"


# Legal transitions. PERSISTED / REJECTED / DUPLICATE / CONFLICT / EXPIRED are
# terminal. EXPIRED is reserved (expiry is not enforced in Phase 5 — see §11).
_TRANSITIONS: dict[SignalState, frozenset[SignalState]] = {
    SignalState.RECEIVED: frozenset(
        {SignalState.VALIDATED, SignalState.REJECTED, SignalState.EXPIRED}
    ),
    SignalState.VALIDATED: frozenset(
        {
            SignalState.ACCEPTED,
            SignalState.REJECTED,
            SignalState.DUPLICATE,
            SignalState.CONFLICT,
            SignalState.EXPIRED,
        }
    ),
    SignalState.ACCEPTED: frozenset(
        {SignalState.PERSISTED, SignalState.DUPLICATE, SignalState.CONFLICT}
    ),
    SignalState.PERSISTED: frozenset(),
    SignalState.REJECTED: frozenset(),
    SignalState.DUPLICATE: frozenset(),
    SignalState.CONFLICT: frozenset(),
    SignalState.EXPIRED: frozenset(),
}

_TERMINAL = frozenset(
    {
        SignalState.PERSISTED,
        SignalState.REJECTED,
        SignalState.DUPLICATE,
        SignalState.CONFLICT,
        SignalState.EXPIRED,
    }
)


class SignalStateMachine:
    """Enforces legal signal-lifecycle transitions (fail-closed)."""

    def __init__(self, initial: SignalState = SignalState.RECEIVED) -> None:
        self._state = initial

    @property
    def state(self) -> SignalState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in _TERMINAL

    def can_transition(self, to: SignalState) -> bool:
        return to in _TRANSITIONS[self._state]

    def transition(self, to: SignalState) -> None:
        if to not in _TRANSITIONS[self._state]:
            raise RuntimeError(f"illegal signal transition: {self._state.value} -> {to.value}")
        self._state = to
