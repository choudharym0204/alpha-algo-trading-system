from __future__ import annotations

from alpha_algo_contracts import MarketCandle, MarketTick


class DataReplayCursor:
    """Deterministic forward-only iteration over explicit historical records.

    The cursor is a pure in-memory sequence reader: it never fetches data,
    never blocks, and never touches any broker, network, or live system. It
    exists so later simulation tasks can consume history in a deterministic
    order without inventing their own iteration logic.
    """

    def __init__(self, records: tuple[MarketCandle | MarketTick, ...]) -> None:
        if not records:
            raise ValueError("replay requires at least one record")
        self._records = records
        self._index = 0

    def peek(self) -> MarketCandle | MarketTick | None:
        if self._index >= len(self._records):
            return None
        return self._records[self._index]

    def next(self) -> MarketCandle | MarketTick | None:
        """Return the next record, or ``None`` when the cursor is exhausted."""
        if self._index >= len(self._records):
            return None
        record = self._records[self._index]
        self._index += 1
        return record

    @property
    def index(self) -> int:
        return self._index

    @property
    def total(self) -> int:
        return len(self._records)

    @property
    def is_exhausted(self) -> bool:
        return self._index >= len(self._records)
