"""Phase 7 orchestration state-machine tests."""

import pytest

from alpha_algo_trading_engine.state import (
    TERMINAL_STATES,
    OrchestrationState,
    OrchestrationStateError,
    OrchestrationStateMachine,
)


def test_golden_path_transitions_are_legal():
    m = OrchestrationStateMachine()
    assert m.state == OrchestrationState.RECEIVED
    assert m.transition(OrchestrationState.VALIDATED) == OrchestrationState.VALIDATED
    assert m.transition(OrchestrationState.RISK_EVALUATED) == OrchestrationState.RISK_EVALUATED
    assert m.transition(OrchestrationState.APPROVED) == OrchestrationState.APPROVED
    assert m.transition(OrchestrationState.OMS_HANDOFF_READY) == OrchestrationState.OMS_HANDOFF_READY
    assert m.is_terminal


def test_rejections_are_legal_from_relevant_states():
    m = OrchestrationStateMachine()
    assert m.transition(OrchestrationState.REJECTED) == OrchestrationState.REJECTED
    assert m.is_terminal

    m2 = OrchestrationStateMachine()
    m2.transition(OrchestrationState.VALIDATED)
    assert m2.transition(OrchestrationState.REJECTED) == OrchestrationState.REJECTED


def test_illegal_transition_raises():
    m = OrchestrationStateMachine()
    with pytest.raises(OrchestrationStateError):
        m.transition(OrchestrationState.APPROVED)  # RECEIVED -> APPROVED is illegal


def test_terminal_states_have_no_outgoing_edges():
    def assert_locked(machine):
        for target in OrchestrationState:
            with pytest.raises(OrchestrationStateError):
                machine.transition(target)

    # REJECTED (reachable from RECEIVED)
    m = OrchestrationStateMachine()
    m.transition(OrchestrationState.REJECTED)
    assert_locked(m)

    # OMS_HANDOFF_READY (reachable via the golden path)
    m = OrchestrationStateMachine()
    m.transition(OrchestrationState.VALIDATED)
    m.transition(OrchestrationState.RISK_EVALUATED)
    m.transition(OrchestrationState.APPROVED)
    m.transition(OrchestrationState.OMS_HANDOFF_READY)
    assert_locked(m)

    # FAILED (reachable from APPROVED)
    m = OrchestrationStateMachine()
    m.transition(OrchestrationState.VALIDATED)
    m.transition(OrchestrationState.RISK_EVALUATED)
    m.transition(OrchestrationState.APPROVED)
    m.transition(OrchestrationState.FAILED)
    assert_locked(m)


def test_terminal_states_set():
    assert TERMINAL_STATES == frozenset(
        {
            OrchestrationState.REJECTED,
            OrchestrationState.FAILED,
            OrchestrationState.DUPLICATE,
            OrchestrationState.OMS_HANDOFF_READY,
        }
    )
