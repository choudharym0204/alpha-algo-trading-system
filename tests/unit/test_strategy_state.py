from __future__ import annotations

import pytest

from alpha_algo_strategy_engine import RunStateMachine, StrategyRunState


def test_valid_lifecycle_transitions() -> None:
    m = RunStateMachine()
    assert m.state == StrategyRunState.CREATED
    m.transition(StrategyRunState.INITIALIZING)
    m.transition(StrategyRunState.CREATED)
    m.transition(StrategyRunState.RUNNING)
    m.transition(StrategyRunState.PAUSED)
    m.transition(StrategyRunState.RUNNING)
    m.transition(StrategyRunState.STOPPING)
    m.transition(StrategyRunState.STOPPED)
    assert m.is_terminal is True


def test_illegal_transition_is_rejected() -> None:
    m = RunStateMachine()
    with pytest.raises(RuntimeError, match="illegal state transition"):
        m.transition(StrategyRunState.PAUSED)  # CREATED -> PAUSED is illegal
    m = RunStateMachine()
    m.transition(StrategyRunState.RUNNING)
    m.transition(StrategyRunState.PAUSED)
    with pytest.raises(RuntimeError):
        m.transition(StrategyRunState.INITIALIZING)  # PAUSED -> INITIALIZING illegal


def test_failed_is_terminal() -> None:
    m = RunStateMachine()
    m.transition(StrategyRunState.FAILED)
    assert m.is_terminal is True
    with pytest.raises(RuntimeError):
        m.transition(StrategyRunState.RUNNING)
