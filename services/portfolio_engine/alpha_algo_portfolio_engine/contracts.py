"""Phase 12 — Portfolio Engine: normalized contracts.

The Portfolio Engine aggregates authoritative Phase-11 position state, account /
funds state, and normalized reference prices into portfolio-level state. Its
inputs are broker-independent; its outputs are immutable read models.

It does NOT compute P&L (Phase 13) and does NOT reconcile (Phase 14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class PortfolioStatus(StrEnum):
    """Smallest useful state model (reflects data validity, never fabricates)."""

    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    DEGRADED = "DEGRADED"  # missing/stale price or funds -> partial, flagged
    ERROR = "ERROR"


class PortfolioCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class PortfolioIdentity:
    """Canonical portfolio key = (broker_account_id, trading_mode).

    Preserves the existing ``portfolio_snapshots`` unique constraint on
    ``(broker_account_id, trading_mode, snapshot_at)``: a portfolio is an
    account-scoped, mode-scoped aggregate; snapshots are time-indexed states of
    that portfolio.
    """

    account_id: UUID
    trading_mode: str

    def as_tuple(self) -> tuple[UUID, str]:
        return (self.account_id, self.trading_mode.upper())


@dataclass(frozen=True)
class PositionInput:
    """A single authoritative position (from the Phase-11 Position Engine).

    ``quantity`` is signed net quantity (positive = long, negative = short).
    Phase 11 is LONG-only, so quantity is always >= 0 in practice; the
    aggregation handles signed quantity generically so the formulas remain
    correct if short support is added later.
    """

    position_id: UUID | None
    instrument_id: UUID
    strategy_run_id: UUID
    quantity: int
    average_price: Decimal | None
    status: str  # OPEN / CLOSED / FLAT

    @property
    def is_open(self) -> bool:
        return self.quantity != 0


@dataclass(frozen=True)
class ReferencePrice:
    """A normalized reference price from the Phase-3 market-data layer."""

    instrument_id: UUID
    price: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.price <= Decimal("0"):
            raise ValueError("reference price must be positive")
        _require_timezone(self.observed_at, "observed_at")


@dataclass(frozen=True)
class FundsState:
    """Normalized account funds/margin state (from a Phase-10 funds snapshot).

    Every field is nullable: unavailable funds are ``None``, never fabricated
    as zero.
    """

    available_cash: Decimal | None = None
    available_margin: Decimal | None = None
    used_margin: Decimal | None = None
    captured_at: datetime | None = None

    @property
    def available(self) -> bool:
        return self.available_cash is not None


@dataclass(frozen=True)
class PositionExposure:
    """Per-position aggregate contribution (for the read model / breakdown)."""

    position_id: UUID | None
    instrument_id: UUID
    strategy_run_id: UUID
    quantity: int
    reference_price: Decimal | None
    market_value: Decimal | None  # quantity * price, None if price unavailable
    price_state: str  # FRESH / STALE / MISSING


@dataclass(frozen=True)
class StrategyBreakdown:
    """Deterministic strategy-level aggregation (derived read, not a separate
    canonical source of truth)."""

    strategy_run_id: UUID
    position_count: int
    market_value: Decimal | None
    gross_exposure: Decimal


@dataclass(frozen=True)
class PortfolioInputs:
    """The complete, authoritative input bundle for one portfolio computation."""

    account_id: UUID
    trading_mode: str
    positions: tuple[PositionInput, ...] = ()
    funds: FundsState | None = None
    prices: dict[UUID, ReferencePrice] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioComputation:
    """The deterministic result of aggregating one portfolio input bundle."""

    identity: PortfolioIdentity
    status: PortfolioStatus
    completeness: PortfolioCompleteness
    position_count: int
    gross_exposure: Decimal
    net_exposure: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    market_value: Decimal | None
    cash_balance: Decimal | None
    equity_value: Decimal | None
    available_margin: Decimal | None
    used_margin: Decimal | None
    funds_available: bool
    missing_instrument_ids: tuple[UUID, ...]
    stale_instrument_ids: tuple[UUID, ...]
    positions: tuple[PositionExposure, ...]
    strategy_breakdown: tuple[StrategyBreakdown, ...]
    snapshot_at: datetime


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Immutable read model of a persisted portfolio snapshot."""

    snapshot_id: UUID | None
    account_id: UUID
    trading_mode: str
    status: PortfolioStatus
    completeness: PortfolioCompleteness
    position_count: int
    gross_exposure: Decimal
    net_exposure: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    market_value: Decimal | None
    cash_balance: Decimal | None
    equity_value: Decimal | None
    available_margin: Decimal | None
    used_margin: Decimal | None
    snapshot_at: datetime


@dataclass(frozen=True)
class PortfolioResult:
    """The outcome of generating + persisting one portfolio snapshot."""

    status: PortfolioStatus
    snapshot: PortfolioSnapshot
    duplicate: bool = False
    computation: PortfolioComputation | None = None
