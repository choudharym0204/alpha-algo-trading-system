"""Shared helpers for Phase 5 signal-engine tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_signal_engine.directory import StrategyRecord


def make_signal(
    *,
    strategy_id: UUID | None = None,
    version: str = "1.0.0",
    config_hash: str | None = None,
    code_hash: str | None = None,
    run_id: UUID | None = None,
    instrument_id: UUID | None = None,
    action: SignalAction = SignalAction.BUY,
    timestamp: datetime | None = None,
    event_timestamp: datetime | None = None,
    confidence: Decimal = Decimal("0.8"),
    reason: str = "test signal",
    metadata: dict | None = None,
    signal_id: UUID | None = None,
) -> StrategySignal:
    ts = timestamp or datetime.now(UTC)
    meta = dict(metadata or {})
    # Traceability marker (Phase-4 enrichment) — present by default so the signal
    # passes ingestion. Tests that want "missing traceability" remove it.
    meta.setdefault("event_timestamp", (event_timestamp or ts).isoformat())
    if code_hash is not None:
        meta.setdefault("strategy_code_hash", code_hash)
    if run_id is not None:
        meta.setdefault("strategy_run_id", str(run_id))
    return StrategySignal(
        signal_id=signal_id or uuid4(),
        strategy_id=strategy_id or uuid4(),
        strategy_version=version,
        strategy_config_hash=config_hash or "0" * 64,
        instrument_id=instrument_id or uuid4(),
        action=action,
        timestamp=ts,
        confidence=confidence,
        reason=reason,
        metadata=meta,
    )


def make_record(
    strategy_id: UUID,
    *,
    version: str = "1.0.0",
    config_hash: str | None = None,
    code_hash: str | None = None,
    enabled: bool = True,
    instruments: frozenset[UUID] | None = None,
) -> StrategyRecord:
    return StrategyRecord(
        strategy_id=strategy_id,
        version=version,
        config_hash=config_hash or "0" * 64,
        code_hash=code_hash,
        enabled=enabled,
        instruments=instruments,
    )


class FakeDirectory:
    def __init__(self, records: list[StrategyRecord] | None = None) -> None:
        self._records: dict[UUID, StrategyRecord] = {
            r.strategy_id: r for r in (records or [])
        }

    def add(self, record: StrategyRecord) -> None:
        self._records[record.strategy_id] = record

    def lookup(self, strategy_id: UUID) -> StrategyRecord | None:
        return self._records.get(strategy_id)


class FakeSession:
    def __init__(self, find_result=None) -> None:
        self.find_result = find_result
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def execute(self, stmt):
        result = self.find_result

        class _Result:
            def scalar_one_or_none(self):
                return result

        return _Result()


class FakeSessionFactory:
    """Returns a fresh FakeSession per call; optionally a sequence of results.

    ``find_results`` is a list consumed one per ``find_by_identity`` call.
    """

    def __init__(self, find_results=None, commit_raises=None) -> None:
        self._find_results = list(find_results or [None])
        self._idx = 0
        self.sessions: list[FakeSession] = []
        self.commit_raises = commit_raises

    def _next_find(self):
        if self._idx < len(self._find_results):
            value = self._find_results[self._idx]
            self._idx += 1
            return value
        return None

    def __call__(self) -> FakeSession:
        session = FakeSession(find_result=self._next_find())
        if self.commit_raises is not None:
            def commit():
                # A failing COMMIT must not mark the transaction as committed.
                raise self.commit_raises

            session.commit = commit
        self.sessions.append(session)
        return session
