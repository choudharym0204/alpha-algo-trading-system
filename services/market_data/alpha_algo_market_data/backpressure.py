"""Bounded queue with an explicit drop policy (backpressure).

The market-data engine enqueues raw events here; when a slow consumer lets the
queue fill up, the drop policy decides what to discard — never silently, because
every drop increments ``dropped_count`` and is surfaced through metrics/logs.
"""

from __future__ import annotations

import asyncio
from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedQueue(Generic[T]):
    def __init__(self, maxsize: int, *, drop_policy: str = "drop_newest") -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if drop_policy not in {"drop_newest", "drop_oldest"}:
            raise ValueError("drop_policy must be 'drop_newest' or 'drop_oldest'")
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self._maxsize = maxsize
        self._drop_policy = drop_policy
        self.dropped_count = 0

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def drop_policy(self) -> str:
        return self._drop_policy

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def full(self) -> bool:
        return self._queue.full()

    def put_nowait(self, item: T) -> bool:
        """Enqueue without blocking.

        Returns True when *item* was accepted; False when *item* (or, under
        ``drop_oldest``, the oldest queued item) was dropped.
        """
        if self._queue.full():
            if self._drop_policy == "drop_oldest":
                self.dropped_count += 1
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    pass
                self._queue.put_nowait(item)
                return True
            # drop_newest: discard the incoming item
            self.dropped_count += 1
            return False
        self._queue.put_nowait(item)
        return True

    async def get(self) -> T:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()
