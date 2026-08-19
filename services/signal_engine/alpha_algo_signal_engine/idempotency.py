"""Idempotency: distinguish new vs duplicate vs conflicting signals.

Two layers enforce idempotency:

1. In-memory bounded LRU (fast path) — ``SignalIdempotency.check`` returns
   ``new`` / ``duplicate`` / ``conflict`` for the same identity key WITHOUT
   mutating state. ``record`` marks an identity as seen only after a successful
   (or authoritatively-duplicate) persist, so a retry after a DB failure is never
   mis-classified as a duplicate of a signal that was never persisted.
2. Persistent DB unique constraint on ``signals.identity_key`` (handled by the
   repository) — guarantees no two accepted records for one logical signal even
   across restarts and concurrent races.

"Duplicate" = same identity + same content (idempotent success).
"Conflict" = same identity + different content (rejected, never overwritten).
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

OUTCOME_NEW = "new"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_CONFLICT = "conflict"


class SignalIdempotency:
    def __init__(self, maxsize: int = 100_000) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = maxsize
        self._seen: OrderedDict[str, str] = OrderedDict()
        self._lock = Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def check(self, identity_key: str, content_hash: str) -> str:
        """Pure lookup — does not record the identity."""
        with self._lock:
            existing = self._seen.get(identity_key)
            if existing is None:
                return OUTCOME_NEW
            self._seen.move_to_end(identity_key)
            return OUTCOME_DUPLICATE if existing == content_hash else OUTCOME_CONFLICT

    def record(self, identity_key: str, content_hash: str) -> None:
        """Mark an identity as seen (call only after a durable outcome)."""
        with self._lock:
            self._seen[identity_key] = content_hash
            self._seen.move_to_end(identity_key)
            if len(self._seen) > self._maxsize:
                self._seen.popitem(last=False)
