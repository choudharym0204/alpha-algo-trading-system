"""Strategy run-state machine and trading-mode enum."""

from __future__ import annotations

from enum import StrEnum
from threading import Lock


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class StrategyRunState(StrEnum):
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


# Legal state transitions. STOPPED and FAILED are terminal.
_TRANSITIONS: dict[StrategyRunState, frozenset[StrategyRunState]] = {
    StrategyRunState.CREATED: frozenset(
        {StrategyRunState.INITIALIZING, StrategyRunState.RUNNING, StrategyRunState.FAILED}
    ),
    StrategyRunState.INITIALIZING: frozenset(
        {StrategyRunState.CREATED, StrategyRunState.FAILED}
    ),
    StrategyRunState.RUNNING: frozenset(
        {StrategyRunState.PAUSED, StrategyRunState.STOPPING, StrategyRunState.FAILED}
    ),
    StrategyRunState.PAUSED: frozenset(
        {StrategyRunState.RUNNING, StrategyRunState.STOPPING, StrategyRunState.FAILED}
    ),
    StrategyRunState.STOPPING: frozenset(
        {StrategyRunState.STOPPED, StrategyRunState.FAILED}
    ),
    StrategyRunState.STOPPED: frozenset(),
    StrategyRunState.FAILED: frozenset(),
}

_TERMINAL = frozenset({StrategyRunState.STOPPED, StrategyRunState.FAILED})


class RunStateMachine:
    """Enforces legal run-state transitions (fail-closed, thread-safe).

    Worker threads run callbacks concurrently, so both the read (`state`,
    `is_terminal`) and the check-and-set (`transition`) are guarded by a lock.
    """

    def __init__(self, initial: StrategyRunState = StrategyRunState.CREATED) -> None:
        self._state = initial
        self._lock = Lock()

    @property
    def state(self) -> StrategyRunState:
        with self._lock:
            return self._state

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._state in _TERMINAL

    def can_transition(self, to: StrategyRunState) -> bool:
        with self._lock:
            return to in _TRANSITIONS[self._state]

    def transition(self, to: StrategyRunState) -> None:
        with self._lock:
            if to not in _TRANSITIONS[self._state]:
                raise RuntimeError(
                    f"illegal state transition: {self._state.value} -> {to.value}"
                )
            self._state = to
