"""Phase 14 — Reconciliation Engine: normalized contracts.

The Reconciliation Engine compares internal authoritative state (OMS/Execution/
Position/Portfolio/P&L) against broker observations (Phase 10 normalized read
models). It classifies matches vs. discrepancies, persists evidence, and
produces controlled recovery actions — it **never** silently overwrites
internal financial truth.

Nothing here contains provider-specific logic or credential values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResolutionStatus(StrEnum):
    DETECTED = "DETECTED"
    CLASSIFIED = "CLASSIFIED"
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATED = "ESCALATED"


class EntityType(StrEnum):
    ORDER = "ORDER"
    EXECUTION = "EXECUTION"
    POSITION = "POSITION"
    FUNDS = "FUNDS"


class ObservationStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class DiscrepancyKind(StrEnum):
    """Deterministic discrepancy classification (smallest useful set)."""

    MATCH = "MATCH"
    INTERNAL_ONLY = "INTERNAL_ONLY"
    BROKER_ONLY = "BROKER_ONLY"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    FEE_MISMATCH = "FEE_MISMATCH"
    AVERAGE_PRICE_MISMATCH = "AVERAGE_PRICE_MISMATCH"
    SIDE_MISMATCH = "SIDE_MISMATCH"
    ORDER_TYPE_MISMATCH = "ORDER_TYPE_MISMATCH"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    INSTRUMENT_MISMATCH = "INSTRUMENT_MISMATCH"
    CASH_MISMATCH = "CASH_MISMATCH"
    MARGIN_MISMATCH = "MARGIN_MISMATCH"
    ORDER_LINK_MISMATCH = "ORDER_LINK_MISMATCH"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    ROUNDING_DIFFERENCE = "ROUNDING_DIFFERENCE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


def _require_tz(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
        raise ValueError(f"{name} must be timezone-aware")


# ---------------------------------------------------------------- observations
@dataclass(frozen=True)
class OrderObservation:
    """A single order observation from one side (internal or broker)."""

    source: str  # "internal" | "broker"
    broker_order_id: str | None
    client_order_id: str | None
    account_id: UUID | None
    instrument_id: UUID | None
    side: str | None
    quantity: int | None
    order_type: str | None
    status: str | None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionObservation:
    source: str
    broker_execution_id: str | None
    execution_id: str | None
    order_id: UUID | None
    broker_order_id: str | None
    account_id: UUID | None
    instrument_id: UUID | None
    side: str | None
    quantity: Decimal | None
    price: Decimal | None
    fees: Decimal | None
    status: str | None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class PositionObservation:
    source: str
    account_id: UUID | None
    instrument_id: UUID | None
    quantity: int
    side: str
    average_price: Decimal | None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class FundsObservation:
    source: str
    account_id: UUID | None
    available_cash: Decimal | None
    available_margin: Decimal | None
    used_margin: Decimal | None
    currency: str = "INR"
    observed_at: datetime | None = None


@dataclass(frozen=True)
class ReconciliationRun:
    """Read model of a reconciliation run."""

    run_id: UUID | None
    account_id: UUID
    broker: str
    trading_mode: str
    scope: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    matched: int = 0
    mismatched: int = 0
    internal_only: int = 0
    broker_only: int = 0
    unknown: int = 0
    unavailable: int = 0
    skipped: int = 0
    conflicts: int = 0
    error: str | None = None


@dataclass(frozen=True)
class Discrepancy:
    """Durable, append-only reconciliation evidence (one per deterministic key)."""

    id: UUID | None
    discrepancy_key: str
    run_id: UUID
    account_id: UUID
    broker: str
    trading_mode: str
    entity_type: EntityType
    entity_id: str
    kind: DiscrepancyKind
    severity: Severity
    internal_state: dict
    broker_state: dict
    resolution_status: ResolutionStatus
    content_hash: str
    observed_at: datetime | None = None


@dataclass(frozen=True)
class RecoveryAction:
    """A proposed corrective action (never executed by the engine)."""

    discrepancy_id: UUID | None
    action_type: str  # "ROUTE_BROKER_FILL" | "ESCALATE" | "NO_ACTION"
    target_boundary: str  # "execution_engine" | "none"
    normalized_fill: dict | None = None
    note: str = ""


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    run: ReconciliationRun
    discrepancies: tuple[Discrepancy, ...] = ()
    recovery_actions: tuple[RecoveryAction, ...] = ()


@dataclass(frozen=True)
class ReconciliationScope:
    account_id: UUID
    broker: str
    trading_mode: str
    domains: frozenset[str] = frozenset({"ORDERS", "EXECUTIONS", "POSITIONS", "FUNDS"})


@dataclass(frozen=True)
class ReconciliationInputs:
    """The internal + broker observation bundle for one reconciliation run."""

    orders_internal: tuple[OrderObservation, ...] = ()
    orders_broker: tuple[OrderObservation, ...] = ()
    executions_internal: tuple[ExecutionObservation, ...] = ()
    executions_broker: tuple[ExecutionObservation, ...] = ()
    positions_internal: tuple[PositionObservation, ...] = ()
    positions_broker: tuple[PositionObservation, ...] = ()
    funds_internal: FundsObservation | None = None
    funds_broker: FundsObservation | None = None
