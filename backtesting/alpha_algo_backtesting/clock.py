from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


@dataclass(frozen=True)
class SimulationClock:
    """Deterministic simulation clock for backtesting.

    This clock is a pure arithmetic value object. It never reads the wall
    clock and has no constructor that falls back to ``datetime.now``: time
    advances only by explicit ``step`` increments applied to an explicit
    ``current`` value. This is a deliberate divergence from the injectable
    clock pattern used by live-facing engines, where ``datetime.now(tz=UTC)``
    is an acceptable default; a simulation clock with a wall-clock default
    would break determinism (see ARCHITECTURE_DECISIONS.md ADR-0006).

    All timestamps are timezone-aware UTC.
    """

    current: datetime
    step: timedelta

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.current):
            raise ValueError("current must be timezone-aware")
        if self.step <= timedelta(0):
            raise ValueError("step must be positive")

    def advance(self, times: int = 1) -> SimulationClock:
        """Return a new clock advanced by ``times`` steps.

        The clock is immutable; ``advance`` never mutates this instance.
        """
        if times < 1:
            raise ValueError("times must be a positive integer")
        return SimulationClock(current=self.current + self.step * times, step=self.step)

    def steps_until(self, target: datetime) -> int:
        """Return the deterministic number of steps from ``current`` to ``target``.

        The count is ``(target - current) // step`` using exact timedelta
        arithmetic; it never reads the wall clock. ``target`` must lie
        exactly on the step grid (``target - current`` must be a whole
        multiple of ``step``); non-aligned targets raise ``ValueError`` so
        callers can never silently mis-schedule events.
        """
        if not _is_timezone_aware(target):
            raise ValueError("target must be timezone-aware")
        if target < self.current:
            raise ValueError("target must not be before current")
        delta = target - self.current
        if delta % self.step != timedelta(0):
            raise ValueError("target must be aligned to the step grid")
        return delta // self.step

    @classmethod
    def start(cls, start_at: datetime, *, step: timedelta) -> SimulationClock:
        return cls(current=start_at, step=step)
