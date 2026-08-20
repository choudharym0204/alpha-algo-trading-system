"""Historical-data quality validation for the backtesting subsystem (P16).

Classifies a raw record sequence into ``valid`` / ``quarantined`` /
``rejected`` buckets **without silently repairing anything**. The classifier
is observational: it reports findings and lets the caller decide how to act
(drop, repair upstream, or refuse the dataset). It never mutates, reorders,
deduplicates, or interpolates records.

Scope: records are already ``MarketCandle``/``MarketTick`` model instances
(the contracts enforce positive prices, candle OHLC range, and timezone-aware
timestamps). The classifier therefore focuses on **sequence-level** quality
the model cannot express, plus a few defensive per-record checks:

- **REJECTED** (the series cannot be a coherent single-instrument input):
  out-of-order timestamps, mixed candle/tick kinds, inconsistent symbol/
  exchange/instrument identity, inconsistent candle timeframe, naive
  timestamps, non-positive/non-finite prices, candle OHLC range violation,
  tick ``bid > ask``.
- **QUARANTINED** (suspicious, needs a policy decision — never auto-fixed):
  duplicate timestamps, future-dated records (vs an injected reference time),
  and gaps (spacing beyond an injected expected step multiple).

``reference_time`` and ``expected_step`` are both optional and both injected —
the classifier never reads the wall clock and never assumes a bar cadence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtest_quality.errors import DataQualityError

__all__ = [
    "DATA_QUALITY_POLICY",
    "DataQualityFinding",
    "DataQualityReport",
    "QualityClass",
    "validate_dataset",
]

DATA_QUALITY_POLICY = (
    "Observational classification into VALID / QUARANTINED / REJECTED. "
    "REJECTED = incoherent series (out-of-order, mixed kinds, identity or "
    "timeframe drift, naive timestamps, invalid prices/OHLC, tick bid>ask). "
    "QUARANTINED = suspicious but repairable-by-policy (duplicate timestamps, "
    "future-dated vs injected reference time, gaps vs injected expected "
    "step). No silent repair, reorder, dedup, or interpolation."
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _record_timestamp(record: MarketCandle | MarketTick) -> datetime:
    if isinstance(record, MarketCandle):
        return record.candle_start
    return record.timestamp


class QualityClass(StrEnum):
    VALID = "VALID"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DataQualityFinding:
    """One classified issue for one record index (or ``-1`` for series-level)."""

    index: int
    classification: QualityClass
    reason: str

    def __post_init__(self) -> None:
        if type(self.index) is not int:
            raise DataQualityError("index must be an int")
        if not isinstance(self.classification, QualityClass):
            raise DataQualityError("classification must be a QualityClass member")
        if not isinstance(self.reason, str) or not self.reason:
            raise DataQualityError("reason must be a non-empty string")


@dataclass(frozen=True)
class DataQualityReport:
    """Aggregate classification of a historical record sequence."""

    total_records: int
    valid_count: int
    quarantined_count: int
    rejected_count: int
    findings: tuple[DataQualityFinding, ...] = field(default_factory=tuple)
    dataset_classification: QualityClass = QualityClass.VALID

    def __post_init__(self) -> None:
        if type(self.total_records) is not int or self.total_records < 0:
            raise DataQualityError("total_records must be a non-negative int")
        for name, value in (
            ("valid_count", self.valid_count),
            ("quarantined_count", self.quarantined_count),
            ("rejected_count", self.rejected_count),
        ):
            if type(value) is not int or value < 0:
                raise DataQualityError(f"{name} must be a non-negative int")
        if self.valid_count + self.quarantined_count + self.rejected_count != self.total_records:
            raise DataQualityError("record classification counts must sum to total_records")
        if not isinstance(self.findings, tuple) or not all(isinstance(f, DataQualityFinding) for f in self.findings):
            raise DataQualityError("findings must be a tuple of DataQualityFinding")
        if not isinstance(self.dataset_classification, QualityClass):
            raise DataQualityError("dataset_classification must be a QualityClass member")

    @property
    def is_simulation_ready(self) -> bool:
        """True only when every record is VALID (no rejected or quarantined)."""
        return self.rejected_count == 0 and self.quarantined_count == 0


def _classify_record(record: MarketCandle | MarketTick, index: int, findings: list[DataQualityFinding]) -> QualityClass:
    """Per-record defensive checks (models should already enforce these)."""
    ts = _record_timestamp(record)
    rejected = False
    if not _is_timezone_aware(ts):
        findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="naive timestamp"))
        rejected = True
    if isinstance(record, MarketCandle):
        for name, value in (("open", record.open_price), ("high", record.high_price), ("low", record.low_price), ("close", record.close_price)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason=f"invalid candle {name}_price"))
                rejected = True
        if record.low_price > record.high_price:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="candle low exceeds high"))
            rejected = True
        if not (record.low_price <= record.open_price <= record.high_price):
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="candle open outside range"))
            rejected = True
        if not (record.low_price <= record.close_price <= record.high_price):
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="candle close outside range"))
            rejected = True
    else:
        if not isinstance(record.ltp, Decimal) or not record.ltp.is_finite() or record.ltp <= 0:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="invalid tick ltp"))
            rejected = True
        if record.bid is not None and record.ask is not None and record.bid > record.ask:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="tick bid exceeds ask"))
            rejected = True
    if rejected:
        return QualityClass.REJECTED
    return QualityClass.VALID


def validate_dataset(
    records: tuple[MarketCandle | MarketTick, ...],
    *,
    reference_time: datetime | None = None,
    expected_step: timedelta | None = None,
    gap_multiple: int = 3,
) -> DataQualityReport:
    """Classify a record sequence into valid/quarantined/rejected.

    Raises :class:`DataQualityError` for malformed calls only; data problems
    are reported as findings. ``reference_time`` enables future-dated
    detection (injected, never wall clock); ``expected_step`` enables gap
    detection (spacing > ``gap_multiple * expected_step`` is QUARANTINED).
    """
    if not isinstance(records, tuple) or not all(isinstance(r, (MarketCandle, MarketTick)) for r in records):
        raise DataQualityError("records must be a tuple of MarketCandle or MarketTick")
    if reference_time is not None and (not isinstance(reference_time, datetime) or not _is_timezone_aware(reference_time)):
        raise DataQualityError("reference_time must be timezone-aware or None")
    if expected_step is not None and (not isinstance(expected_step, timedelta) or expected_step <= timedelta(0)):
        raise DataQualityError("expected_step must be a positive timedelta or None")
    if type(gap_multiple) is not int or gap_multiple < 1:
        raise DataQualityError("gap_multiple must be a positive int")

    findings: list[DataQualityFinding] = []
    classes: list[QualityClass] = []

    first = records[0] if records else None
    first_is_candle = isinstance(first, MarketCandle)
    first_identity: tuple | None = None
    first_timeframe = None
    if first is not None:
        first_identity = (first.instrument_id, first.exchange, first.symbol)
        if first_is_candle:
            first_timeframe = first.timeframe

    previous_ts: datetime | None = None

    for index, record in enumerate(records):
        per_record = _classify_record(record, index, findings)
        ts = _record_timestamp(record)

        # Series-level identity coherence.
        identity = (record.instrument_id, record.exchange, record.symbol)
        if identity != first_identity:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="symbol/exchange/instrument identity drift"))
        if first_is_candle != isinstance(record, MarketCandle):
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="mixed candle/tick kinds"))
        if first_is_candle and isinstance(record, MarketCandle) and record.timeframe != first_timeframe:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="candle timeframe drift"))

        # Sequence-level ordering / duplicates / future / gaps.
        if previous_ts is not None:
            if ts < previous_ts:
                findings.append(DataQualityFinding(index=index, classification=QualityClass.REJECTED, reason="out-of-order timestamp"))
            elif ts == previous_ts:
                findings.append(DataQualityFinding(index=index, classification=QualityClass.QUARANTINED, reason="duplicate timestamp"))
            elif expected_step is not None and (ts - previous_ts) > expected_step * gap_multiple:
                findings.append(DataQualityFinding(index=index, classification=QualityClass.QUARANTINED, reason="gap larger than expected step"))
        if reference_time is not None and ts > reference_time:
            findings.append(DataQualityFinding(index=index, classification=QualityClass.QUARANTINED, reason="future-dated record"))

        # A record is REJECTED if any of its findings are REJECTED.
        record_rejected = any(f.index == index and f.classification is QualityClass.REJECTED for f in findings)
        record_quarantined = any(f.index == index and f.classification is QualityClass.QUARANTINED for f in findings)
        if per_record is QualityClass.REJECTED or record_rejected:
            classes.append(QualityClass.REJECTED)
        elif record_quarantined:
            classes.append(QualityClass.QUARANTINED)
        else:
            classes.append(QualityClass.VALID)

        previous_ts = ts

    valid_count = sum(1 for c in classes if c is QualityClass.VALID)
    quarantined_count = sum(1 for c in classes if c is QualityClass.QUARANTINED)
    rejected_count = sum(1 for c in classes if c is QualityClass.REJECTED)

    if rejected_count > 0:
        dataset_classification = QualityClass.REJECTED
    elif quarantined_count > 0:
        dataset_classification = QualityClass.QUARANTINED
    else:
        dataset_classification = QualityClass.VALID

    return DataQualityReport(
        total_records=len(records),
        valid_count=valid_count,
        quarantined_count=quarantined_count,
        rejected_count=rejected_count,
        findings=tuple(findings),
        dataset_classification=dataset_classification,
    )
