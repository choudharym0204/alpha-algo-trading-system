from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from alpha_algo_backtesting import SimulationClock

START = datetime(2026, 1, 2, 9, 15, tzinfo=UTC)
STEP = timedelta(minutes=1)


def test_clock_advances_by_explicit_steps() -> None:
    clock = SimulationClock.start(START, step=STEP)

    advanced = clock.advance(3)

    assert advanced.current == datetime(2026, 1, 2, 9, 18, tzinfo=UTC)


def test_clock_is_immutable_and_deterministic() -> None:
    clock = SimulationClock.start(START, step=STEP)

    advanced = clock.advance()

    assert clock.current == START  # original instance unchanged
    assert advanced.current == START + STEP

    # Same start and steps always produce the same sequence.
    first = SimulationClock.start(START, step=STEP).advance(2).advance(1)
    second = SimulationClock.start(START, step=STEP).advance(3)
    assert first.current == second.current


def test_clock_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="step must be positive"):
        SimulationClock.start(START, step=timedelta(0))
    with pytest.raises(ValueError, match="step must be positive"):
        SimulationClock.start(START, step=timedelta(seconds=-1))


def test_clock_rejects_naive_current() -> None:
    with pytest.raises(ValueError, match="current must be timezone-aware"):
        SimulationClock(current=datetime(2026, 1, 2, 9, 15), step=STEP)


def test_clock_advance_rejects_non_positive_times() -> None:
    clock = SimulationClock.start(START, step=STEP)

    with pytest.raises(ValueError, match="times must be a positive integer"):
        clock.advance(0)
    with pytest.raises(ValueError, match="times must be a positive integer"):
        clock.advance(-1)


def test_steps_until_is_deterministic() -> None:
    clock = SimulationClock.start(START, step=STEP)

    assert clock.steps_until(datetime(2026, 1, 2, 9, 18, tzinfo=UTC)) == 3


def test_steps_until_zero_for_current() -> None:
    clock = SimulationClock.start(START, step=STEP)

    assert clock.steps_until(START) == 0


def test_steps_until_round_trips_with_advance() -> None:
    clock = SimulationClock.start(START, step=STEP)
    target = datetime(2026, 1, 2, 9, 18, tzinfo=UTC)

    assert clock.advance(clock.steps_until(target)).current == target


def test_steps_until_rejects_non_aligned_target() -> None:
    clock = SimulationClock.start(START, step=STEP)

    with pytest.raises(ValueError, match="aligned to the step grid"):
        clock.steps_until(datetime(2026, 1, 2, 9, 18, 30, tzinfo=UTC))


def test_steps_until_rejects_naive_or_backward_target() -> None:
    clock = SimulationClock.start(START, step=STEP)

    with pytest.raises(ValueError, match="target must be timezone-aware"):
        clock.steps_until(datetime(2026, 1, 2, 9, 18))
    with pytest.raises(ValueError, match="target must not be before current"):
        clock.steps_until(START - timedelta(minutes=1))
