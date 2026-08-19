from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

from alpha_algo_contracts import MarketTick


@dataclass(frozen=True)
class StaleDataDecision:
    is_stale: bool
    age: timedelta
    reason: str


def evaluate_staleness(
    tick: MarketTick,
    *,
    now: datetime,
    max_age: timedelta,
) -> StaleDataDecision:
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")

    age = now - tick.timestamp
    if age < timedelta(0):
        return StaleDataDecision(
            is_stale=True,
            age=age,
            reason="tick_timestamp_in_future",
        )
    if age > max_age:
        return StaleDataDecision(
            is_stale=True,
            age=age,
            reason="tick_timestamp_stale",
        )
    return StaleDataDecision(
        is_stale=False,
        age=age,
        reason="tick_timestamp_fresh",
    )


class DuplicateTickDetector:
    """Duplicate detection with bounded memory (LRU eviction).

    ``maxsize=None`` keeps the historical unbounded behavior (backward
    compatible); a positive ``maxsize`` bounds the number of tracked
    ``(broker, sequence)`` keys so memory does not grow indefinitely under a
    live tick stream.
    """

    def __init__(self, maxsize: int | None = None) -> None:
        if maxsize is not None and maxsize < 1:
            raise ValueError("maxsize must be >= 1 or None")
        self._maxsize = maxsize
        self._seen_sequences: OrderedDict[tuple[str, str], None] = OrderedDict()

    def __len__(self) -> int:
        return len(self._seen_sequences)

    def is_duplicate(self, tick: MarketTick) -> bool:
        key = (tick.source_broker, tick.source_sequence)
        if key in self._seen_sequences:
            self._seen_sequences.move_to_end(key)
            return True
        self._seen_sequences[key] = None
        if self._maxsize is not None and len(self._seen_sequences) > self._maxsize:
            self._seen_sequences.popitem(last=False)
        return False

