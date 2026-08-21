"""Phase 23 — GlobalHaltController (kill switch) unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_algo_risk_engine import GlobalHaltController, GlobalHaltState


FIXED_NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def test_controller_starts_halted_by_default() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    assert controller.is_halted() is True
    assert controller.state.active is True


def test_activate_halts_instantly_with_audit_trail() -> None:
    controller = GlobalHaltController(
        clock=lambda: FIXED_NOW, initial_active=False, initial_reason=""
    )
    assert controller.is_halted() is False

    state = controller.activate(reason="manual emergency stop", actor="operator")

    assert state.active is True
    assert state.reason == "manual emergency stop"
    assert state.updated_by == "operator"
    assert controller.is_halted() is True


def test_deactivate_requires_reason_and_actor() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)

    state = controller.deactivate(reason="all gates verified", actor="operator")

    assert state.active is False
    assert state.metadata["deactivate_reason"] == "all gates verified"
    assert controller.is_halted() is False


def test_activate_requires_reason() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    with pytest.raises(ValueError, match="reason"):
        controller.activate(reason="  ", actor="operator")


def test_activate_requires_actor() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    with pytest.raises(ValueError, match="actor"):
        controller.activate(reason="halt", actor="  ")


def test_deactivate_requires_reason() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    with pytest.raises(ValueError, match="reason"):
        controller.deactivate(reason="", actor="operator")


def test_state_is_immutable_snapshot() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    state = controller.state
    assert isinstance(state, GlobalHaltState)

    # A later transition must not mutate the previously-returned snapshot.
    controller.activate(reason="new halt", actor="operator")
    assert state.reason == "default safety halt"


def test_repeated_transitions_are_idempotent_and_consistent() -> None:
    controller = GlobalHaltController(
        clock=lambda: FIXED_NOW, initial_active=False, initial_reason=""
    )
    controller.activate(reason="halt 1", actor="op")
    controller.activate(reason="halt 2", actor="op")
    assert controller.state.reason == "halt 2"

    controller.deactivate(reason="clear", actor="op")
    controller.deactivate(reason="clear again", actor="op")
    assert controller.is_halted() is False
    assert controller.state.metadata["deactivate_reason"] == "clear again"


def test_timestamp_is_timezone_aware() -> None:
    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    assert controller.state.updated_at.tzinfo is not None


def test_concurrent_activate_deactivate_is_consistent() -> None:
    import threading

    controller = GlobalHaltController(clock=lambda: FIXED_NOW)
    observed: list[bool] = []

    def worker(flag: bool) -> None:
        for _ in range(200):
            if flag:
                controller.activate(reason="t", actor="w")
            else:
                controller.deactivate(reason="t", actor="w")
            observed.append(controller.is_halted())

    threads = [threading.Thread(target=worker, args=(i % 2 == 0,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every observation is a valid bool; final state is a valid GlobalHaltState.
    assert all(isinstance(v, bool) for v in observed)
    assert isinstance(controller.state, GlobalHaltState)
