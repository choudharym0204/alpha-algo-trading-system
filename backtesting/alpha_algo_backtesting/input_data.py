from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtesting.hashing import content_sha256


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _record_timestamp(record: MarketCandle | MarketTick) -> datetime:
    if isinstance(record, MarketCandle):
        return record.candle_start
    return record.timestamp


@dataclass(frozen=True)
class BacktestInput:
    """Explicit historical market data for a backtest run.

    The input accepts only explicitly provided records: there is no default
    dataset and no embedded sample data anywhere in this package, so nothing
    here can be mistaken for real market data (non-negotiable trading rule 2).

    Validation is strict and fail-loud: empty, unsorted, duplicated, mixed,
    or internally incoherent inputs are rejected at construction. Records are
    never silently reordered or deduplicated; the manifest is a promise that
    the simulation consumed exactly this history.

    Timestamps are treated as explicit history with no recency check:
    records are never compared against a wall clock, so future-dated or
    historical-extended series are accepted exactly as given. Any
    "no data newer than X" policy must be an injected, deterministic
    reference-time policy evaluated by the caller, never a wall-clock read
    inside this package.
    """

    dataset_id: str
    source: str
    records: tuple[MarketCandle | MarketTick, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.records:
            raise ValueError("backtest requires at least one data record")

        first = self.records[0]
        first_is_candle = isinstance(first, MarketCandle)
        for index, record in enumerate(self.records):
            if isinstance(record, MarketCandle) != first_is_candle:
                raise ValueError("records must all be the same kind (all candles or all ticks)")
            if not _is_timezone_aware(_record_timestamp(record)):
                raise ValueError("record timestamps must be timezone-aware")
            if record.instrument_id != first.instrument_id:
                raise ValueError("records must share a single instrument")
            if record.exchange != first.exchange:
                raise ValueError("records must share a single exchange")
            if record.symbol != first.symbol:
                raise ValueError("records must share a single symbol")
            if first_is_candle:
                assert isinstance(record, MarketCandle)
                assert isinstance(first, MarketCandle)
                if record.timeframe != first.timeframe:
                    raise ValueError("candles must share a single timeframe")
            if index > 0:
                previous = self.records[index - 1]
                previous_ts = _record_timestamp(previous)
                current_ts = _record_timestamp(record)
                if current_ts < previous_ts:
                    raise ValueError(f"records must be sorted ascending by timestamp (index {index})")
                if current_ts == previous_ts:
                    raise ValueError(f"duplicate record timestamp at index {index}")
            if isinstance(record, MarketTick) and record.bid is not None and record.ask is not None:
                if record.bid > record.ask:
                    raise ValueError(f"tick bid cannot exceed ask (index {index})")

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def first_timestamp(self) -> datetime:
        return _record_timestamp(self.records[0])

    @property
    def last_timestamp(self) -> datetime:
        return _record_timestamp(self.records[-1])

    @property
    def records_kind(self) -> str:
        if isinstance(self.records[0], MarketCandle):
            return "candles"
        return "ticks"

    @property
    def symbol_counts(self) -> tuple[tuple[str, int], ...]:
        """Sorted per-symbol record counts (deterministic iteration order)."""
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.symbol] = counts.get(record.symbol, 0) + 1
        return tuple(sorted(counts.items()))

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.records)
