"""Backtest persistence and result caching (P16) — an optional outer layer.

Persistence is deliberately an **outer concern**: the core backtest is a pure
deterministic computation and never depends on this package. A
:class:`BacktestRecord` snapshots the run identity, status, configuration,
metrics, and an optional report reference, and round-trips through a stable
JSON encoding with integrity validation. A :class:`BacktestStore` (in-memory
double provided) keys records by the deterministic identity digest, so the
same deterministic input maps to a reproducible, cacheable result and a
conflicting payload for the same identity is refused rather than silently
overwritten.

No database, no network, no broker, no live data: persistence here is a
plain, auditable serialization contract a caller can hand to any sink.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from alpha_algo_backtest_persistence.errors import PersistenceError

__all__ = [
    "PERSISTENCE_POLICY",
    "BacktestRecord",
    "BacktestStatus",
    "BacktestStore",
    "InMemoryBacktestStore",
    "cache_key_for_identity",
]

PERSISTENCE_POLICY = (
    "Optional outer-layer persistence. BacktestRecord snapshots identity + "
    "status + configuration + metrics + report reference as stable JSON with "
    "integrity validation. BacktestStore keys by deterministic identity "
    "digest; duplicate identity -> no-op, conflicting payload -> PersistenceError. "
    "No database/network/broker/live data; core backtest never depends on it."
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


class BacktestStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _pairs_to_sorted_list(pairs: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return sorted([[str(k), str(v)] for k, v in pairs])


@dataclass(frozen=True)
class BacktestRecord:
    """A persisted snapshot of one backtest run (metadata + result summary)."""

    run_id: UUID
    identity_sha256: str
    status: BacktestStatus
    created_at: datetime
    report_reference: str | None = None
    configuration: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    metrics: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise PersistenceError("run_id must be a UUID")
        if not isinstance(self.identity_sha256, str) or len(self.identity_sha256) != 64:
            raise PersistenceError("identity_sha256 must be a 64-char hex string")
        if not isinstance(self.status, BacktestStatus):
            raise PersistenceError("status must be a BacktestStatus member")
        if not isinstance(self.created_at, datetime) or not _is_timezone_aware(self.created_at):
            raise PersistenceError("created_at must be a timezone-aware datetime")
        if self.report_reference is not None and not isinstance(self.report_reference, str):
            raise PersistenceError("report_reference must be a string or None")
        for name, value in (("configuration", self.configuration), ("metrics", self.metrics)):
            if not isinstance(value, tuple):
                raise PersistenceError(f"{name} must be a tuple of (key, value) pairs")
            for pair in value:
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise PersistenceError(f"{name} must contain (key, value) pairs")
        # Normalize to canonical sorted order so two records with the same
        # key/value pairs (in any order) compare and serialize identically.
        object.__setattr__(self, "configuration", tuple(sorted(self.configuration)))
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics)))

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "identity_sha256": self.identity_sha256,
            "status": self.status.value,
            "created_at": self.created_at.astimezone(UTC).isoformat(timespec="microseconds"),
            "report_reference": self.report_reference,
            "configuration": _pairs_to_sorted_list(self.configuration),
            "metrics": _pairs_to_sorted_list(self.metrics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> BacktestRecord:
        """Reconstruct a record from its JSON encoding (validated, fail-loud)."""
        if not isinstance(text, str) or not text:
            raise PersistenceError("text must be a non-empty JSON string")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PersistenceError(f"corrupted metadata: invalid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise PersistenceError("corrupted metadata: top-level JSON must be an object")

        def _required_str(key: str) -> str:
            value = data.get(key)
            if not isinstance(value, str) or not value:
                raise PersistenceError(f"corrupted metadata: missing {key!r}")
            return value

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            if value is None:
                return None
            if not isinstance(value, str):
                raise PersistenceError(f"corrupted metadata: {key!r} must be a string or null")
            return value

        def _pairs(key: str) -> tuple[tuple[str, str], ...]:
            value = data.get(key, [])
            if not isinstance(value, list):
                raise PersistenceError(f"corrupted metadata: {key!r} must be a list")
            pairs = []
            for item in value:
                if not isinstance(item, list) or len(item) != 2:
                    raise PersistenceError(f"corrupted metadata: {key!r} entries must be [key, value]")
                pairs.append((str(item[0]), str(item[1])))
            return tuple(pairs)

        try:
            run_id = UUID(_required_str("run_id"))
            status = BacktestStatus(_required_str("status"))
            created_at = datetime.fromisoformat(_required_str("created_at"))
        except (ValueError, TypeError) as exc:
            raise PersistenceError(f"corrupted metadata: {exc}") from exc

        return cls(
            run_id=run_id,
            identity_sha256=_required_str("identity_sha256"),
            status=status,
            created_at=created_at,
            report_reference=_optional_str("report_reference"),
            configuration=_pairs("configuration"),
            metrics=_pairs("metrics"),
        )


def cache_key_for_identity(identity_sha256: str) -> str:
    """Return the cache key (the identity digest) for a backtest result."""
    if not isinstance(identity_sha256, str) or len(identity_sha256) != 64:
        raise PersistenceError("identity_sha256 must be a 64-char hex string")
    return identity_sha256


class BacktestStore:
    """Abstract persistence store keyed by deterministic identity digest."""

    def save(self, record: BacktestRecord) -> BacktestRecord:
        raise NotImplementedError

    def load(self, identity_sha256: str) -> BacktestRecord | None:
        raise NotImplementedError

    def contains(self, identity_sha256: str) -> bool:
        raise NotImplementedError


class InMemoryBacktestStore(BacktestStore):
    """A dict-backed store with duplicate/conflict semantics (no I/O)."""

    def __init__(self) -> None:
        self._records: dict[str, BacktestRecord] = {}

    def save(self, record: BacktestRecord) -> BacktestRecord:
        if not isinstance(record, BacktestRecord):
            raise PersistenceError("record must be a BacktestRecord")
        key = record.identity_sha256
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = record
            return record
        if existing.run_id != record.run_id:
            raise PersistenceError("same identity with a different run id is a conflict")
        if existing.to_json() != record.to_json():
            raise PersistenceError("same identity with a different payload is a conflict (original preserved)")
        return existing

    def load(self, identity_sha256: str) -> BacktestRecord | None:
        key = cache_key_for_identity(identity_sha256)
        return self._records.get(key)

    def contains(self, identity_sha256: str) -> bool:
        key = cache_key_for_identity(identity_sha256)
        return key in self._records

    def __len__(self) -> int:
        return len(self._records)
