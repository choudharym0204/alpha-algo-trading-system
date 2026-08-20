"""Deterministic backtest run identity for persistence (P16).

A backtest run identity is a canonical, order-stable digest of every
result-affecting immutable input. The same deterministic input maps to the
same identity (and the same ``run_id`` via a namespace UUID5), so a past run
can be reproduced and its result cache keyed unambiguously.

Volatile fields (wall-clock timestamps, audit ``created_at``) are deliberately
**excluded** from the identity: they are metadata and never affect simulation
math. A ``seed``, when present, is included so a seeded Monte Carlo / latency
run is a distinct, reproducible identity.

The canonical serialization is owned by this package (explicit field order,
``Decimal`` via ``str``, UTC-normalized ISO-8601 timestamps, explicit ``None``)
and must never be replaced with ``repr``/``str(dict)``/``hash()``.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from alpha_algo_backtest_persistence.errors import PersistenceError

__all__ = [
    "IDENTITY_POLICY",
    "SIMULATOR_VERSION",
    "BacktestRunIdentity",
    "identity_sha256",
    "run_id_for_identity",
]

SIMULATOR_VERSION = "P16-1"

IDENTITY_POLICY = (
    "Canonical, order-stable SHA-256 over immutable result-affecting inputs "
    "(dataset id/source/input hash, strategy identity/version/config hash, "
    "cost model, initial capital, start/end period, instrument universe, "
    "simulator version, seed). Wall-clock/audit timestamps are excluded; a "
    "seed is included when present so seeded runs are distinct identities."
)

_NAMESPACE = uuid.UUID("5c9d8f7e-6b5a-4c3d-9e2f-1a0b9c8d7e6f")


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _canonical(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, str)):
        return str(value)
    raise PersistenceError(f"unsupported identity value type: {type(value).__name__}")


@dataclass(frozen=True)
class BacktestRunIdentity:
    """The immutable fingerprint of one deterministic backtest run."""

    dataset_id: str
    source: str
    input_sha256: str
    simulator_version: str = SIMULATOR_VERSION
    strategy_identity: str | None = None
    strategy_version: str | None = None
    configuration_hash: str | None = None
    initial_capital: Decimal | None = None
    commission_per_fill: Decimal | None = None
    slippage_bps: Decimal | None = None
    risk_free_rate_per_period: Decimal | None = None
    periods_per_year: int | None = None
    seed: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    instrument_universe: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name, value in (("dataset_id", self.dataset_id), ("source", self.source)):
            if not isinstance(value, str) or not value:
                raise PersistenceError(f"{name} must be a non-empty string")
        if not isinstance(self.input_sha256, str) or len(self.input_sha256) != 64:
            raise PersistenceError("input_sha256 must be a 64-char hex string")
        if not isinstance(self.simulator_version, str) or not self.simulator_version:
            raise PersistenceError("simulator_version must be a non-empty string")
        for name, value in (
            ("strategy_identity", self.strategy_identity),
            ("strategy_version", self.strategy_version),
            ("configuration_hash", self.configuration_hash),
            ("seed", self.seed),
        ):
            if value is not None and not isinstance(value, str):
                raise PersistenceError(f"{name} must be a string or None")
        if self.initial_capital is not None and (
            not isinstance(self.initial_capital, Decimal)
            or not self.initial_capital.is_finite()
            or self.initial_capital <= 0
        ):
            raise PersistenceError("initial_capital must be a positive finite Decimal or None")
        for name, value in (
            ("commission_per_fill", self.commission_per_fill),
            ("slippage_bps", self.slippage_bps),
            ("risk_free_rate_per_period", self.risk_free_rate_per_period),
        ):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise PersistenceError(f"{name} must be a non-negative finite Decimal or None")
        if self.periods_per_year is not None and (type(self.periods_per_year) is not int or self.periods_per_year < 1):
            raise PersistenceError("periods_per_year must be a positive int or None")
        for name, value in (("start_at", self.start_at), ("end_at", self.end_at)):
            if value is not None and (not isinstance(value, datetime) or not _is_timezone_aware(value)):
                raise PersistenceError(f"{name} must be a timezone-aware datetime or None")
        if not isinstance(self.instrument_universe, tuple):
            raise PersistenceError("instrument_universe must be a tuple")
        for item in self.instrument_universe:
            if not isinstance(item, str):
                raise PersistenceError("instrument_universe must contain only strings")

    def canonical_string(self) -> str:
        """Order-stable canonical serialization of every identity field."""
        fields = (
            ("dataset_id", self.dataset_id),
            ("source", self.source),
            ("input_sha256", self.input_sha256),
            ("simulator_version", self.simulator_version),
            ("strategy_identity", self.strategy_identity),
            ("strategy_version", self.strategy_version),
            ("configuration_hash", self.configuration_hash),
            ("initial_capital", self.initial_capital),
            ("commission_per_fill", self.commission_per_fill),
            ("slippage_bps", self.slippage_bps),
            ("risk_free_rate_per_period", self.risk_free_rate_per_period),
            ("periods_per_year", self.periods_per_year),
            ("seed", self.seed),
            ("start_at", self.start_at),
            ("end_at", self.end_at),
            ("instrument_universe", "\x1f".join(sorted(self.instrument_universe))),
        )
        return "|".join(f"{name}={_canonical(value)}" for name, value in fields)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_string().encode("utf-8")).hexdigest()

    def run_id(self) -> uuid.UUID:
        return run_id_for_identity(self.canonical_string())


def identity_sha256(identity: BacktestRunIdentity) -> str:
    """Return the deterministic digest for a backtest run identity."""
    if not isinstance(identity, BacktestRunIdentity):
        raise PersistenceError("identity must be a BacktestRunIdentity")
    return identity.sha256()


def run_id_for_identity(canonical: str) -> uuid.UUID:
    """Derive a stable run id (namespace UUID5) from a canonical string."""
    if not isinstance(canonical, str) or not canonical:
        raise PersistenceError("canonical must be a non-empty string")
    return uuid.uuid5(_NAMESPACE, canonical)
