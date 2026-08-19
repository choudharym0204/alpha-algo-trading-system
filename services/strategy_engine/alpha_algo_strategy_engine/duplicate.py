"""Bounded duplicate-signal protection (deterministic identity, thread-safe)."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from datetime import datetime
from threading import Lock

from alpha_algo_contracts import StrategySignal


def signal_dedup_key(signal: StrategySignal, event_timestamp: datetime) -> str:
    """Deterministic identity of a signal for duplicate detection.

    Two signals are the same only if the same strategy (id/version/config) emits
    the same action for the same instrument triggered by the same event
    timestamp. A genuinely new event (different timestamp) never collides.

    Invariant: at most ONE accepted signal per (instrument, action) per event is
    supported. A strategy that intentionally emits multiple signals for the same
    instrument+action from a single event must disambiguate them (e.g. distinct
    reason) — otherwise the second is treated as a replay/duplicate and dropped.
    This is the deliberate trade-off that makes replay/reconnect/retry dedup
    deterministic (a re-delivered event yields the same key).
    """
    raw = (
        str(signal.strategy_id),
        signal.strategy_version,
        signal.strategy_config_hash,
        str(signal.instrument_id),
        signal.action.value,
        event_timestamp.isoformat(),
    )
    return hashlib.sha256("|".join(raw).encode("utf-8")).hexdigest()


class SignalDeduplicator:
    """Bounded LRU of seen dedup keys (bounded memory, like the Phase-3 dedup)."""

    def __init__(self, maxsize: int = 100_000) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = maxsize
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def is_duplicate(self, signal: StrategySignal, event_timestamp: datetime) -> bool:
        key = signal_dedup_key(signal, event_timestamp)
        with self._lock:
            if key in self._seen:
                self._seen.move_to_end(key)
                return True
            self._seen[key] = None
            if len(self._seen) > self._maxsize:
                self._seen.popitem(last=False)
            return False
