"""Immutable risk snapshot + freshness semantics (Phase 6).

A ``RiskSnapshot`` is the single, coherent, immutable view of authoritative
runtime state used for one deterministic risk evaluation. It captures the
portfolio/account/exposure/P&L/market state and the configured limits at the
moment the decision is made. Individual fields default to ``None`` to mean
"not provided", which the rules treat as fail-closed (REJECT), never as zero
or unlimited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware")
    return value


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: UUID | None = None
    available_funds: Decimal | None = None
    equity: Decimal | None = None
    high_water_mark: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    daily_realized_pnl: Decimal | None = None
    strategy_realized_pnl: Decimal | None = None
    current_drawdown: Decimal | None = None
    available_margin: Decimal | None = None
    used_margin: Decimal | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    instrument_id: UUID | None = None
    reference_price: Decimal | None = None
    current_price: Decimal | None = None
    market_data_fresh: bool = False
    broker_connected: bool = False
    market_session_open: bool = False
    instrument_allowed: bool = False
    last_update_at: datetime | None = None


@dataclass(frozen=True)
class PositionSnapshot:
    open_positions_count: int | None = None
    position_quantity: Decimal | None = None
    projected_position_quantity: Decimal | None = None
    exposure: Decimal | None = None
    reserved_quantity: Decimal | None = None
    pending_order_count: int | None = None


@dataclass(frozen=True)
class LimitsSnapshot:
    max_order_quantity: Decimal | None = None
    max_position_quantity: Decimal | None = None
    max_exposure: Decimal | None = None
    max_daily_loss: Decimal | None = None
    max_strategy_loss: Decimal | None = None
    max_open_positions: int | None = None
    max_drawdown: Decimal | None = None
    max_price_deviation: Decimal | None = None
    max_orders_per_window: int | None = None
    order_window_seconds: int | None = None
    # Account-level limits (independent of strategy-level).
    account_max_order_quantity: Decimal | None = None
    account_max_positions: int | None = None
    account_max_exposure: Decimal | None = None
    account_max_loss: Decimal | None = None
    account_max_order_rate: int | None = None
    # Execution timeout + retry safety.
    max_unresolved_executions: int | None = None
    max_retries_per_signal: int | None = None


@dataclass(frozen=True)
class OrderFrequencySnapshot:
    recent_order_count: int | None = None
    window_started_at: datetime | None = None


@dataclass(frozen=True)
class RiskSnapshot:
    snapshot_id: UUID = field(default_factory=uuid4)
    taken_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    source: str = "unavailable"
    state_available: bool = False
    max_age: timedelta | None = None
    global_halt_active: bool = True
    trading_mode: str = "PAPER"
    live_trading_enabled: bool = False
    duplicate_signal: bool = False
    account: AccountSnapshot = field(default_factory=AccountSnapshot)
    market: MarketSnapshot = field(default_factory=MarketSnapshot)
    positions: PositionSnapshot = field(default_factory=PositionSnapshot)
    limits: LimitsSnapshot = field(default_factory=LimitsSnapshot)
    frequency: OrderFrequencySnapshot = field(default_factory=OrderFrequencySnapshot)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.taken_at)

    def is_stale(self, now: datetime) -> bool:
        """A snapshot is stale when older than ``max_age`` (None = never stale).

        A future-dated ``taken_at`` (clock skew) is also treated as stale, so a
        skewed provider clock cannot make a snapshot appear indefinitely fresh.
        """
        _require_aware(now)
        if self.max_age is None:
            return False
        age = now - self.taken_at
        return age > self.max_age or age < timedelta(0)
