"""Window construction for the walk-forward testing harness (P7-003).

``build_windows`` slices an explicit P7-001 :class:`BacktestInput` into
strictly forward, strictly disjoint train/validation/test segments. Windows
are counted in records, never in calendar time: the harness has no calendar
model and never assumes uniform spacing (the ADR-0009 precedent). Every
window is uniform and complete; a trailing remainder shorter than one step
is unused, never truncated, and always visible through the coverage
metadata reported by ``run_walk_forward``. Test windows never overlap
across periods (``step_records >= test_records`` is enforced at
construction), so out-of-sample periods stay independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_backtesting import BacktestInput

from alpha_algo_walk_forward.errors import WalkForwardError

__all__ = [
    "WINDOW_SCHEDULE_POLICY",
    "WalkForwardConfig",
    "WalkForwardWindow",
    "WindowSlice",
    "build_windows",
]

WINDOW_SCHEDULE_POLICY = (
    "Uniform rolling windows: every window covers exactly training+validation+test "
    "contiguous records in strictly ascending order; the test slice always starts "
    "after train+val within its window; test windows never overlap across periods "
    "(step_records >= test_records, enforced at config construction); a trailing "
    "remainder shorter than one step is unused, never truncated, and reported in the "
    "run's coverage metadata; fewer than one full window of data fails loudly."
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _record_timestamp(record: MarketCandle | MarketTick) -> datetime:
    if isinstance(record, MarketCandle):
        return record.candle_start
    return record.timestamp


@dataclass(frozen=True)
class WalkForwardConfig:
    """Window geometry, in record counts.

    All four fields are required (no defaults) and must be exact ``int``
    values (``bool`` and numpy integers are rejected, never coerced).
    ``step_records >= test_records`` is enforced here so that out-of-sample
    windows can never overlap across periods.
    """

    training_records: int
    validation_records: int
    test_records: int
    step_records: int

    def __post_init__(self) -> None:
        for name, value in (
            ("training_records", self.training_records),
            ("validation_records", self.validation_records),
            ("test_records", self.test_records),
            ("step_records", self.step_records),
        ):
            if type(value) is not int:
                raise WalkForwardError(f"{name} must be an int (bool and non-int values are rejected, never coerced)")
            if value < 1:
                raise WalkForwardError(f"{name} must be at least 1")
        if self.step_records < self.test_records:
            raise WalkForwardError(
                "step_records must be >= test_records so out-of-sample windows never overlap across periods"
            )


@dataclass(frozen=True)
class WindowSlice:
    """One contiguous segment of the explicit history.

    ``start_index`` is inclusive, ``end_index`` is exclusive (half-open
    ``[start, end)``); ``start_timestamp`` is the timestamp of the first
    record and ``end_timestamp`` is the timestamp of the last record
    (inclusive), so ``start_timestamp <= ts <= end_timestamp`` selects
    exactly the slice's records. Timestamps are derived from the records
    themselves, never from a clock.
    """

    start_index: int
    end_index: int
    start_timestamp: datetime
    end_timestamp: datetime

    def __post_init__(self) -> None:
        for name, value in (("start_index", self.start_index), ("end_index", self.end_index)):
            if type(value) is not int:
                raise WalkForwardError(f"{name} must be an int")
        if self.start_index < 0:
            raise WalkForwardError("start_index must be non-negative")
        if self.end_index <= self.start_index:
            raise WalkForwardError("end_index must be strictly greater than start_index (slices are never empty)")
        for name, value in (("start_timestamp", self.start_timestamp), ("end_timestamp", self.end_timestamp)):
            if not isinstance(value, datetime) or not _is_timezone_aware(value):
                raise WalkForwardError(f"{name} must be a timezone-aware datetime")
        if self.start_timestamp > self.end_timestamp:
            raise WalkForwardError("start_timestamp must not be after end_timestamp")


@dataclass(frozen=True)
class WalkForwardWindow:
    """One walk-forward period: train, validation, and test segments.

    ``train``/``validation``/``test`` describe index ranges and timestamp
    boundaries; ``train_input``/``validation_input``/``test_input`` are
    fresh, re-validated P7-001 slices (each with its own ``content_sha256``)
    built from the same record objects the caller provided — never copies.
    Segments are contiguous within the window (``train.end == validation.start
    == test.start - ...``), strictly ordered, and strictly disjoint, so no
    period can observe records outside its own slice (no look-ahead).
    Cross-period overlap is legal and intended: a later window's train may
    re-cover an earlier window's test records; each period is evaluated
    independently over its own slice.
    """

    index: int
    train: WindowSlice
    validation: WindowSlice
    test: WindowSlice
    train_input: BacktestInput
    validation_input: BacktestInput
    test_input: BacktestInput

    def __post_init__(self) -> None:
        if type(self.index) is not int:
            raise WalkForwardError("index must be an int")
        if self.index < 0:
            raise WalkForwardError("index must be non-negative")
        for name, value in (
            ("train", self.train),
            ("validation", self.validation),
            ("test", self.test),
        ):
            if not isinstance(value, WindowSlice):
                raise WalkForwardError(f"{name} must be a WindowSlice")
        if self.train.end_index != self.validation.start_index:
            raise WalkForwardError("train and validation must be contiguous (no intra-window gaps)")
        if self.validation.end_index != self.test.start_index:
            raise WalkForwardError("validation and test must be contiguous (no intra-window gaps)")
        if not self.train.start_index < self.test.end_index:
            raise WalkForwardError("window slices must be strictly ordered (train before validation before test)")
        if not self.train.start_timestamp < self.validation.end_timestamp < self.test.end_timestamp:
            raise WalkForwardError("window boundary timestamps must be strictly increasing")
        for name, value in (
            ("train_input", self.train_input),
            ("validation_input", self.validation_input),
            ("test_input", self.test_input),
        ):
            if not isinstance(value, BacktestInput):
                raise WalkForwardError(f"{name} must be a BacktestInput")
        expected = (
            ("train_input", self.train_input, self.train),
            ("validation_input", self.validation_input, self.validation),
            ("test_input", self.test_input, self.test),
        )
        for name, value, slice_ in expected:
            if value.record_count != slice_.end_index - slice_.start_index:
                raise WalkForwardError(f"{name} record count does not match its slice range")
            if value.first_timestamp != slice_.start_timestamp:
                raise WalkForwardError(f"{name} first timestamp does not match its slice start")
            if value.last_timestamp != slice_.end_timestamp:
                raise WalkForwardError(f"{name} last timestamp does not match its slice end")

    @property
    def in_sample(self) -> WindowSlice:
        """Union of train and validation (``[train.start, validation.end)``).

        In-sample means train ∪ validation; out-of-sample means the test
        slice. Contiguous by construction. Derived, not stored.
        """
        return WindowSlice(
            start_index=self.train.start_index,
            end_index=self.validation.end_index,
            start_timestamp=self.train.start_timestamp,
            end_timestamp=self.validation.end_timestamp,
        )

    @property
    def in_sample_input(self) -> BacktestInput:
        """Fresh validated input covering exactly the in-sample records."""
        return BacktestInput(
            dataset_id=self.train_input.dataset_id,
            source=self.train_input.source,
            records=self.train_input.records + self.validation_input.records,
            metadata=self.train_input.metadata,
        )


def build_windows(*, inputs: BacktestInput, config: WalkForwardConfig) -> tuple[WalkForwardWindow, ...]:
    """Build the complete walk-forward schedule (pure, deterministic).

    Identical ``(inputs, config)`` yield an identical tuple of windows.
    Records are never re-sorted, deduplicated, copied, or modified; the
    input is never changed. A dataset shorter than one full window fails
    loudly; a trailing remainder shorter than one step is simply outside
    the schedule and is reported by the run's coverage metadata.
    """
    if not isinstance(inputs, BacktestInput):
        raise WalkForwardError("inputs must be a BacktestInput")
    if not isinstance(config, WalkForwardConfig):
        raise WalkForwardError("config must be a WalkForwardConfig")

    record_count = inputs.record_count
    span = config.training_records + config.validation_records + config.test_records
    if record_count < span:
        raise WalkForwardError(
            f"cannot form a single full window: {record_count} records available, {span} required"
        )

    period_count = (record_count - span) // config.step_records + 1
    windows: list[WalkForwardWindow] = []
    for index in range(period_count):
        start = index * config.step_records
        train_end = start + config.training_records
        validation_end = train_end + config.validation_records
        test_end = validation_end + config.test_records

        def _slice(begin: int, end: int) -> WindowSlice:
            return WindowSlice(
                start_index=begin,
                end_index=end,
                start_timestamp=_record_timestamp(inputs.records[begin]),
                end_timestamp=_record_timestamp(inputs.records[end - 1]),
            )

        windows.append(
            WalkForwardWindow(
                index=index,
                train=_slice(start, train_end),
                validation=_slice(train_end, validation_end),
                test=_slice(validation_end, test_end),
                train_input=BacktestInput(
                    dataset_id=inputs.dataset_id,
                    source=inputs.source,
                    records=inputs.records[start:train_end],
                    metadata=inputs.metadata,
                ),
                validation_input=BacktestInput(
                    dataset_id=inputs.dataset_id,
                    source=inputs.source,
                    records=inputs.records[train_end:validation_end],
                    metadata=inputs.metadata,
                ),
                test_input=BacktestInput(
                    dataset_id=inputs.dataset_id,
                    source=inputs.source,
                    records=inputs.records[validation_end:test_end],
                    metadata=inputs.metadata,
                ),
            )
        )
    return tuple(windows)
