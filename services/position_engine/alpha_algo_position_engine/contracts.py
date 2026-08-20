"""Phase 11 — Position Engine: normalized contracts.

The Position Engine consumes **normalized execution/fill events** — never
broker-specific payloads. Its input is ``PositionFill`` (a fully-resolved,
broker-independent fill produced by the Execution Engine handoff); its output is
``PositionSnapshot`` (an immutable read model) and ``PositionResult`` (the apply
outcome).

Everything here is a frozen dataclass with ``__post_init__`` validation, so
invalid input fails at construction rather than corrupting position state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class PositionStatus(StrEnum):
    """Smallest lifecycle compatible with the existing ``positions`` schema.

    Derived consistently from net quantity + lifecycle semantics:

    * ``FLAT``   — no open position (net quantity == 0, no authoritative row).
    * ``OPEN``   — net quantity != 0.
    * ``CLOSED`` — an opened position fully reduced to zero (closed_at set).

    ``PARTIALLY_CLOSED`` is deliberately **not** a stored state: it is derivable
    from the append-only event trail (a ``POSITION_DECREASED`` event while the
    row remains ``OPEN``).
    """

    FLAT = "FLAT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PositionSide(StrEnum):
    """Signed-quantity side. Phase 11 is LONG-only (no short, no flip)."""

    LONG = "LONG"
    SHORT = "SHORT"


class PositionEventType(StrEnum):
    """Append-only position events persisted per authoritative fill."""

    POSITION_OPENED = "POSITION_OPENED"
    POSITION_INCREASED = "POSITION_INCREASED"
    POSITION_DECREASED = "POSITION_DECREASED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_CONFLICT = "POSITION_CONFLICT"
    POSITION_ERROR = "POSITION_ERROR"


class PositionApplyStatus(StrEnum):
    """Outcome of a single fill application."""

    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class PositionFill:
    """A normalized, broker-independent execution/fill event.

    This is the contract crossing the Execution-Engine → Position-Engine
    boundary. It carries the durable execution identity (idempotency key), the
    fill economics, and the resolved position-identity dimensions. It never
    carries broker tokens, broker symbols, or raw provider payloads.
    """

    execution_id: str
    order_id: UUID
    account_id: UUID
    instrument_id: UUID
    strategy_run_id: UUID
    trading_mode: str
    side: str
    quantity: Decimal
    price: Decimal
    occurred_at: datetime
    broker_order_id: str | None = None
    fill_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id is required")
        if not self.trading_mode.strip():
            raise ValueError("trading_mode is required")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"side must be BUY or SELL, got {self.side!r}")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.price <= Decimal("0"):
            raise ValueError("price must be positive")
        _require_timezone(self.occurred_at, "occurred_at")


@dataclass(frozen=True)
class PositionSnapshot:
    """Immutable read model of current position state (never mutates state)."""

    position_id: UUID | None
    account_id: UUID | None
    instrument_id: UUID
    strategy_run_id: UUID
    trading_mode: str
    side: PositionSide | None
    quantity: int
    average_price: Decimal | None
    status: PositionStatus
    opened_at: datetime | None
    closed_at: datetime | None
    last_execution_id: str | None

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0


@dataclass(frozen=True)
class PositionResult:
    """The outcome of applying one normalized fill."""

    status: PositionApplyStatus
    event_type: PositionEventType | None
    snapshot: PositionSnapshot
    quantity_before: int = 0
    quantity_after: int = 0
    duplicate: bool = False
    conflict: bool = False


@dataclass(frozen=True)
class PositionIdentity:
    """Deterministic position key (account/strategy-run + instrument + mode)."""

    strategy_run_id: UUID
    instrument_id: UUID
    trading_mode: str

    def as_tuple(self) -> tuple[UUID, UUID, str]:
        return (self.strategy_run_id, self.instrument_id, self.trading_mode)


@dataclass(frozen=True)
class PositionState:
    """Pure in-memory projection of a position row (used by the engine)."""

    position_id: UUID | None
    strategy_run_id: UUID
    instrument_id: UUID
    trading_mode: str
    quantity: int = 0
    average_price: Decimal | None = None
    status: PositionStatus = PositionStatus.FLAT
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    last_execution_id: str | None = None
    account_id: UUID | None = None
    extra: dict[str, object] = field(default_factory=dict)
