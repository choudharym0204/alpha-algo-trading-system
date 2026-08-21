"""Phase 13 — P&L Engine: normalized contracts.

The P&L Engine derives **realized** and **unrealized** P&L from authoritative
execution/position facts (Phase 11) + normalized reference prices (Phase 3/12),
plus explicitly-supplied costs. It is broker-independent and does NOT reconcile
(Phase 14), does NOT submit orders, and never enables LIVE.

All money math is ``Decimal``; quantity is whole-share ``int``; every dataclass
validates at construction so invalid financial inputs fail fast.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class PnlStatus(StrEnum):
    """Smallest useful P&L validity state (never fabricates)."""

    READY = "READY"            # realized fact, or unrealized from a fresh price
    DEGRADED = "DEGRADED"      # unrealized from a stale/future price
    UNAVAILABLE = "UNAVAILABLE"  # no usable reference price
    CONFLICT = "CONFLICT"


class PnlEventType(StrEnum):
    """Append-only accounting event kinds."""

    REALIZED_PNL = "REALIZED_PNL"
    COST_APPLIED = "COST_APPLIED"
    PNL_CONFLICT = "PNL_CONFLICT"
    PNL_REJECTED = "PNL_REJECTED"


class PnlApplyStatus(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class PriceState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class CostComponent:
    """A single explicitly-supplied transaction cost (fee/commission/charge).

    Never invented: only present when a provider/normalized source supplies it.
    """

    amount: Decimal
    kind: str = "commission"
    source: str = "broker"

    def __post_init__(self) -> None:
        if self.amount < Decimal("0"):
            raise ValueError("cost amount must be non-negative")
        if not self.kind.strip():
            raise ValueError("cost kind is required")


@dataclass(frozen=True)
class RealizedPnl:
    """Deterministic realized P&L for one closing (SELL) fill."""

    execution_id: str
    account_id: UUID
    strategy_run_id: UUID
    instrument_id: UUID
    trading_mode: str
    closed_quantity: int
    sell_price: Decimal
    average_cost: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    occurred_at: datetime


@dataclass(frozen=True)
class UnrealizedPnl:
    """Mark-to-market unrealized P&L for an open position."""

    position_id: UUID | None
    instrument_id: UUID
    quantity: int
    average_cost: Decimal | None
    reference_price: Decimal | None
    unrealized_pnl: Decimal | None  # None when price unavailable
    price_state: PriceState
    status: PnlStatus


@dataclass(frozen=True)
class PositionPnl:
    """Position-level P&L read model (derived, never a competing position truth)."""

    position_id: UUID | None
    account_id: UUID | None
    strategy_run_id: UUID
    instrument_id: UUID
    trading_mode: str
    quantity: int
    average_cost: Decimal | None
    reference_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    realized_pnl: Decimal  # cumulative realized for this position (sum of events)
    status: PnlStatus


@dataclass(frozen=True)
class PnlEvent:
    """Durable, append-only accounting event (one per execution identity)."""

    id: UUID | None
    execution_id: str
    event_type: PnlEventType
    account_id: UUID
    strategy_run_id: UUID
    instrument_id: UUID
    position_id: UUID | None
    trading_mode: str
    side: str
    quantity: int
    price: Decimal | None
    average_cost: Decimal | None
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    occurred_at: datetime
    content_hash: str


@dataclass(frozen=True)
class PnlSnapshot:
    """Durable account-scoped P&L snapshot (read model)."""

    snapshot_id: UUID | None
    account_id: UUID
    trading_mode: str
    snapshot_at: datetime
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    position_count: int
    status: PnlStatus


@dataclass(frozen=True)
class PnlResult:
    """Outcome of recording one fill's accounting effect."""

    status: PnlApplyStatus
    event: PnlEvent | None = None
    realized: RealizedPnl | None = None
    conflict_original: PnlEvent | None = None


@dataclass(frozen=True)
class AggregatedPnl:
    """A strategy/account/portfolio aggregation bucket (no double-counting)."""

    key: str
    realized_gross: Decimal
    realized_costs: Decimal
    realized_net: Decimal
    unrealized_pnl: Decimal | None = None
    gross_pnl: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    trade_count: int = 0
