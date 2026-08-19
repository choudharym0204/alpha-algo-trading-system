"""Phase 5 signal state machine (deterministic, transition-safe)."""

from __future__ import annotations

import pytest

from alpha_algo_signal_engine.state import SignalState, SignalStateMachine


def test_happy_path_transitions() -> None:
    m = SignalStateMachine()
    assert m.state == SignalState.RECEIVED
    m.transition(SignalState.VALIDATED)
    m.transition(SignalState.ACCEPTED)
    m.transition(SignalState.PERSISTED)
    assert m.state == SignalState.PERSISTED
    assert m.is_terminal


def test_rejected_and_expired_from_received() -> None:
    for target in (SignalState.REJECTED, SignalState.EXPIRED):
        m = SignalStateMachine()
        m.transition(target)
        assert m.state == target
        assert m.is_terminal


def test_duplicate_conflict_from_validated() -> None:
    for target in (SignalState.DUPLICATE, SignalState.CONFLICT):
        m = SignalStateMachine()
        m.transition(SignalState.VALIDATED)
        m.transition(target)
        assert m.state == target
        assert m.is_terminal


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (SignalState.RECEIVED, SignalState.ACCEPTED),
        (SignalState.RECEIVED, SignalState.PERSISTED),
        (SignalState.RECEIVED, SignalState.DUPLICATE),
        (SignalState.VALIDATED, SignalState.PERSISTED),
        (SignalState.ACCEPTED, SignalState.REJECTED),
        (SignalState.ACCEPTED, SignalState.ACCEPTED),
        (SignalState.PERSISTED, SignalState.RECEIVED),
        (SignalState.REJECTED, SignalState.ACCEPTED),
        (SignalState.DUPLICATE, SignalState.PERSISTED),
        (SignalState.EXPIRED, SignalState.VALIDATED),
    ],
)
def test_invalid_transitions_fail_safely(from_state: SignalState, to_state: SignalState) -> None:
    m = SignalStateMachine(initial=from_state)
    with pytest.raises(RuntimeError):
        m.transition(to_state)
    assert m.state == from_state


def test_can_transition_reflects_legality() -> None:
    m = SignalStateMachine()
    assert m.can_transition(SignalState.VALIDATED)
    assert not m.can_transition(SignalState.PERSISTED)
