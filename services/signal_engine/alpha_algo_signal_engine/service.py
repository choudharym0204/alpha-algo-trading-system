"""Signal Engine — the dedicated signal-processing boundary between the Phase-4
Strategy Runtime and the future Risk Engine.

Flow (single signal):
    StrategySignal -> validate (directory + mode + traceability)
                   -> deterministic identity + content hash
                   -> idempotency (new / duplicate / conflict)
                   -> transactional persist (SQLAlchemy -> PostgreSQL ``signals``)
                   -> PERSISTED / DUPLICATE / CONFLICT / REJECTED / EXPIRED

It does NOT submit orders, touch brokers/positions/portfolio, or enable LIVE.
Downstream consumers (Phase 6 Risk) are exposed through ``add_consumer`` but not
implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import StrategySignal
from alpha_algo_signal_engine.directory import StrategyDirectory
from alpha_algo_signal_engine.errors import SignalRejectedError, TradingModeError
from alpha_algo_signal_engine.idempotency import (
    OUTCOME_CONFLICT,
    OUTCOME_DUPLICATE,
    SignalIdempotency,
)
from alpha_algo_signal_engine.identity import (
    compute_signal_content_hash,
    compute_signal_identity_key,
    event_timestamp,
)
from alpha_algo_signal_engine.metrics import SignalMetrics
from alpha_algo_signal_engine.repository import (
    OUTCOME_INSERTED,
    SignalRepository,
    to_orm_signal,
)
from alpha_algo_signal_engine.state import SignalState, SignalStateMachine
from alpha_algo_signal_engine.validation import SignalIngestionValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalRecord:
    """A persisted signal record handed to downstream (Phase-6) consumers."""

    signal: StrategySignal
    record_id: UUID
    identity_key: str
    state: SignalState


@dataclass(frozen=True)
class SignalIngestResult:
    state: SignalState
    persisted: bool = False
    reason: str = ""
    signal_id: UUID | None = None
    identity_key: str | None = None
    record_id: UUID | None = None


SignalConsumer = Callable[[SignalRecord], None]


class SignalEngine:
    def __init__(
        self,
        *,
        directory: StrategyDirectory,
        repository: SignalRepository,
        metrics: SignalMetrics | None = None,
        validator: SignalIngestionValidator | None = None,
        idempotency: SignalIdempotency | None = None,
        clock: Callable[[], datetime] | None = None,
        max_signal_age: timedelta | None = None,
    ) -> None:
        self._directory = directory
        self._repository = repository
        self._metrics = metrics or SignalMetrics()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_signal_age = max_signal_age
        self._validator = validator or SignalIngestionValidator(
            directory, clock=self._clock
        )
        self._idempotency = idempotency or SignalIdempotency()
        self._consumers: list[SignalConsumer] = []

    @property
    def metrics(self) -> SignalMetrics:
        return self._metrics

    @property
    def idempotency(self) -> SignalIdempotency:
        return self._idempotency

    def set_directory(self, directory: StrategyDirectory) -> None:
        self._directory = directory
        self._validator = SignalIngestionValidator(directory, clock=self._clock)

    def add_consumer(self, consumer: SignalConsumer) -> None:
        self._consumers.append(consumer)

    def ingest(
        self,
        signal: StrategySignal,
        *,
        trading_mode: str = "PAPER",
    ) -> SignalIngestResult:
        self._metrics.inc("signals_received")
        self._metrics.record_key("per_strategy", str(signal.strategy_id))
        self._metrics.record_key("per_instrument", str(signal.instrument_id))
        start = perf_counter()
        machine = SignalStateMachine()  # RECEIVED
        try:
            # 1. Validate (raises TradingModeError for LIVE; rejections otherwise).
            try:
                self._validator.validate(signal, trading_mode)
                machine.transition(SignalState.VALIDATED)
            except TradingModeError:
                raise  # fail-closed: propagate LIVE rejection loudly
            except SignalRejectedError as exc:
                machine.transition(SignalState.REJECTED)
                self._metrics.inc("signals_rejected")
                return SignalIngestResult(
                    state=machine.state, reason=exc.reason, signal_id=signal.signal_id
                )

            identity_key = compute_signal_identity_key(signal)
            content_hash = compute_signal_content_hash(signal)

            # 2. Expiry (disabled by default in Phase 5 — design ready for Phase 6).
            if self._max_signal_age is not None:
                if self._clock() - event_timestamp(signal) > self._max_signal_age:
                    machine.transition(SignalState.EXPIRED)
                    self._metrics.inc("signals_expired")
                    return SignalIngestResult(
                        state=machine.state,
                        reason="expired",
                        signal_id=signal.signal_id,
                        identity_key=identity_key,
                    )

            # 3. Idempotency (in-memory fast path; pure lookup).
            outcome = self._idempotency.check(identity_key, content_hash)
            if outcome == OUTCOME_DUPLICATE:
                machine.transition(SignalState.DUPLICATE)
                self._metrics.inc("signals_duplicate")
                return SignalIngestResult(
                    state=machine.state,
                    reason="duplicate",
                    signal_id=signal.signal_id,
                    identity_key=identity_key,
                )
            if outcome == OUTCOME_CONFLICT:
                machine.transition(SignalState.CONFLICT)
                self._metrics.inc("signals_conflict")
                return SignalIngestResult(
                    state=machine.state,
                    reason="conflict",
                    signal_id=signal.signal_id,
                    identity_key=identity_key,
                )

            # 4. Persist (transactional; COMMIT is the boundary of truth). The
            # identity is NOT recorded until a durable outcome, so a retry after
            # a DB failure re-attempts persistence instead of a false duplicate.
            machine.transition(SignalState.ACCEPTED)
            orm = to_orm_signal(
                signal,
                identity_key=identity_key,
                content_hash=content_hash,
                state=SignalState.PERSISTED.value,
                processed_at=self._clock(),
            )
            try:
                persist_outcome = self._repository.persist(orm)
            except Exception as exc:  # noqa: BLE001 - DB failure → no false SUCCESS
                self._metrics.inc("persistence_failures")
                logger.warning("signal persistence failed: %s", exc)
                return SignalIngestResult(
                    state=SignalState.ACCEPTED,
                    persisted=False,
                    reason="persistence_failure",
                    signal_id=signal.signal_id,
                    identity_key=identity_key,
                )

            if persist_outcome == OUTCOME_INSERTED:
                machine.transition(SignalState.PERSISTED)
                self._idempotency.record(identity_key, content_hash)
                self._metrics.inc("signals_persisted")
                self._metrics.inc("signals_accepted")
                self._fan_out(
                    SignalRecord(
                        signal=signal,
                        record_id=orm.id,
                        identity_key=identity_key,
                        state=machine.state,
                    )
                )
                return SignalIngestResult(
                    state=machine.state,
                    persisted=True,
                    signal_id=signal.signal_id,
                    identity_key=identity_key,
                    record_id=orm.id,
                )
            if persist_outcome == OUTCOME_DUPLICATE:
                machine.transition(SignalState.DUPLICATE)
                self._idempotency.record(identity_key, content_hash)
                self._metrics.inc("signals_duplicate")
                return SignalIngestResult(
                    state=machine.state,
                    reason="duplicate",
                    signal_id=signal.signal_id,
                    identity_key=identity_key,
                )
            machine.transition(SignalState.CONFLICT)
            self._metrics.inc("signals_conflict")
            return SignalIngestResult(
                state=machine.state,
                reason="conflict",
                signal_id=signal.signal_id,
                identity_key=identity_key,
            )
        finally:
            self._metrics.record_latency(perf_counter() - start)

    def ingest_many(
        self,
        signals: list[StrategySignal],
        *,
        trading_mode: str = "PAPER",
    ) -> list[SignalIngestResult]:
        """Process a batch with per-signal failure isolation.

        A malformed/persisting-failure signal never loses or crashes the others.
        """
        return [self._ingest_isolated(s, trading_mode) for s in signals]

    def _ingest_isolated(self, signal: StrategySignal, trading_mode: str) -> SignalIngestResult:
        try:
            return self.ingest(signal, trading_mode=trading_mode)
        except TradingModeError:
            raise
        except Exception as exc:  # noqa: BLE001 - isolate unexpected faults
            self._metrics.inc("signals_rejected")
            logger.warning("unexpected signal processing error: %s", exc)
            return SignalIngestResult(
                state=SignalState.REJECTED, reason="unexpected_error", signal_id=signal.signal_id
            )

    def _fan_out(self, record: SignalRecord) -> None:
        for consumer in self._consumers:
            try:
                consumer(record)
            except Exception as exc:  # noqa: BLE001 - isolate consumer faults
                logger.warning("signal consumer failed: %s", exc)
