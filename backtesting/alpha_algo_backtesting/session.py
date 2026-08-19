from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Mapping
from uuid import UUID, uuid4

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtesting.clock import SimulationClock
from alpha_algo_backtesting.hashing import (
    CANONICAL_SERIALIZER_VERSION,
    MANIFEST_SCHEMA_VERSION,
)
from alpha_algo_backtesting.input_data import BacktestInput
from alpha_algo_backtesting.mode import BacktestTradingMode
from alpha_algo_backtesting.replay import DataReplayCursor


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


@dataclass(frozen=True)
class InputManifest:
    """Auditable fingerprint of the explicit historical input to a run."""

    schema_version: str
    serializer_version: str
    dataset_id: str
    source: str
    record_count: int
    records_kind: str
    first_timestamp: datetime
    last_timestamp: datetime
    content_sha256: str
    per_symbol_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.first_timestamp):
            raise ValueError("first_timestamp must be timezone-aware")
        if not _is_timezone_aware(self.last_timestamp):
            raise ValueError("last_timestamp must be timezone-aware")


@dataclass(frozen=True)
class BacktestAuditRecord:
    """Audit metadata for one backtest session.

    ``created_at`` comes exclusively from the injected audit clock (the only
    wall-clock read in the whole backtesting package) and is metadata only:
    it is excluded from the input manifest and never feeds simulation math.
    """

    run_id: UUID
    created_at: datetime
    mode: BacktestTradingMode
    input_manifest: InputManifest
    start_at: datetime
    end_at: datetime
    step: timedelta
    caller_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _is_timezone_aware(self.created_at):
            raise ValueError("created_at must be timezone-aware")
        if not _is_timezone_aware(self.start_at):
            raise ValueError("start_at must be timezone-aware")
        if not _is_timezone_aware(self.end_at):
            raise ValueError("end_at must be timezone-aware")


class BacktestSession:
    """Mode-locked, read-only backtesting session foundation.

    The session is deliberately minimal. It accepts explicit historical
    inputs, runs a deterministic simulation clock, replays records forward,
    and produces an audit record. It contains no fills, orders, positions,
    P&L, slippage, or commission logic — those are later simulation-engine
    tasks and must never be added to this foundation.

    Least privilege: the constructor takes no credentials, no environment
    variables, no network clients, no database sessions, and no file paths;
    the session performs no I/O of any kind.
    """

    def __init__(
        self,
        *,
        inputs: BacktestInput,
        step: timedelta,
        trading_mode: BacktestTradingMode = BacktestTradingMode.BACKTEST,
        run_id: UUID | None = None,
        audit_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if trading_mode is not BacktestTradingMode.BACKTEST:
            raise ValueError("backtest sessions can only run in BACKTEST mode")
        if step <= timedelta(0):
            raise ValueError("step must be positive")

        resolved_clock = audit_clock if audit_clock is not None else (lambda: datetime.now(tz=UTC))
        created_at = resolved_clock()
        if not _is_timezone_aware(created_at):
            raise ValueError("audit clock must return a timezone-aware datetime")

        self._inputs = inputs
        self._step = step
        self._run_id = run_id if run_id is not None else uuid4()
        self._created_at = created_at
        self._clock = SimulationClock.start(inputs.first_timestamp, step=step)
        self._cursor = DataReplayCursor(inputs.records)
        self._manifest = InputManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            serializer_version=CANONICAL_SERIALIZER_VERSION,
            dataset_id=inputs.dataset_id,
            source=inputs.source,
            record_count=inputs.record_count,
            records_kind=inputs.records_kind,
            first_timestamp=inputs.first_timestamp,
            last_timestamp=inputs.last_timestamp,
            content_sha256=inputs.content_sha256,
            per_symbol_counts=inputs.symbol_counts,
        )
        self._audit = BacktestAuditRecord(
            run_id=self._run_id,
            created_at=self._created_at,
            mode=trading_mode,
            input_manifest=self._manifest,
            start_at=inputs.first_timestamp,
            end_at=inputs.last_timestamp,
            step=step,
            caller_metadata=dict(inputs.metadata),
        )

    @property
    def mode(self) -> BacktestTradingMode:
        return BacktestTradingMode.BACKTEST

    def manifest(self) -> InputManifest:
        return self._manifest

    def audit(self) -> BacktestAuditRecord:
        return self._audit

    def current_time(self) -> datetime:
        """Simulation time from the deterministic clock (never wall time)."""
        return self._clock.current

    def advance(self, times: int = 1) -> None:
        """Advance the deterministic simulation clock by ``times`` steps."""
        self._clock = self._clock.advance(times)

    def peek_next(self) -> MarketCandle | MarketTick | None:
        return self._cursor.peek()

    def next_record(self) -> MarketCandle | MarketTick | None:
        return self._cursor.next()

    @property
    def is_exhausted(self) -> bool:
        return self._cursor.is_exhausted

    @property
    def records_consumed(self) -> int:
        return self._cursor.index
