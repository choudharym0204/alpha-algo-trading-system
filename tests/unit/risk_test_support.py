"""Shared helpers for Phase 6 risk-engine tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_risk_engine.snapshot import (
    AccountSnapshot,
    LimitsSnapshot,
    MarketSnapshot,
    OrderFrequencySnapshot,
    PositionSnapshot,
    RiskSnapshot,
)
from alpha_algo_risk_engine.state import RiskStateProvider

from signal_test_support import FakeSession, FakeSessionFactory, make_signal  # noqa: F401


def make_snapshot(
    *,
    state_available: bool = True,
    global_halt_active: bool = False,
    trading_mode: str = "PAPER",
    live_trading_enabled: bool = False,
    duplicate_signal: bool = False,
    taken_at: datetime | None = None,
    max_age: timedelta | None = None,
    account: AccountSnapshot | None = None,
    market: MarketSnapshot | None = None,
    positions: PositionSnapshot | None = None,
    limits: LimitsSnapshot | None = None,
    frequency: OrderFrequencySnapshot | None = None,
    snapshot_id: UUID | None = None,
) -> RiskSnapshot:
    return RiskSnapshot(
        snapshot_id=snapshot_id or uuid4(),
        taken_at=taken_at or datetime.now(UTC),
        source="test",
        state_available=state_available,
        max_age=max_age,
        global_halt_active=global_halt_active,
        trading_mode=trading_mode,
        live_trading_enabled=live_trading_enabled,
        duplicate_signal=duplicate_signal,
        account=account or healthy_account(),
        market=market or healthy_market(),
        positions=positions or healthy_positions(),
        limits=limits or healthy_limits(),
        frequency=frequency or OrderFrequencySnapshot(recent_order_count=0),
        metadata={},
    )


def healthy_account(**overrides) -> AccountSnapshot:
    base = dict(
        available_funds=Decimal("100000"),
        equity=Decimal("100000"),
        high_water_mark=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        daily_realized_pnl=Decimal("0"),
        strategy_realized_pnl=Decimal("0"),
        current_drawdown=Decimal("0"),
        available_margin=Decimal("100000"),
        used_margin=Decimal("0"),
    )
    base.update(overrides)
    return AccountSnapshot(**base)


def healthy_market(**overrides) -> MarketSnapshot:
    base = dict(
        reference_price=Decimal("100"),
        current_price=Decimal("100"),
        market_data_fresh=True,
        broker_connected=True,
        market_session_open=True,
        instrument_allowed=True,
    )
    base.update(overrides)
    return MarketSnapshot(**base)


def healthy_positions(**overrides) -> PositionSnapshot:
    base = dict(
        open_positions_count=0,
        position_quantity=Decimal("0"),
        projected_position_quantity=Decimal("0"),
        exposure=Decimal("0"),
        reserved_quantity=Decimal("0"),
        pending_order_count=0,
    )
    base.update(overrides)
    return PositionSnapshot(**base)


def healthy_limits(**overrides) -> LimitsSnapshot:
    base = dict(
        max_order_quantity=Decimal("1000"),
        max_position_quantity=Decimal("1000"),
        max_exposure=Decimal("1000000"),
        max_daily_loss=Decimal("5000"),
        max_strategy_loss=Decimal("5000"),
        max_open_positions=10,
        max_drawdown=Decimal("0.20"),
        max_price_deviation=Decimal("0.10"),
        max_orders_per_window=100,
        order_window_seconds=60,
        max_unresolved_executions=10,
        max_retries_per_signal=5,
    )
    base.update(overrides)
    return LimitsSnapshot(**base)


class FakeRiskProvider(RiskStateProvider):
    def __init__(self, snapshot: RiskSnapshot | None = None) -> None:
        self.snapshot = snapshot or make_snapshot()
        self.calls: list[tuple] = []

    def get_snapshot(self, *, account_id=None, instrument_id=None, strategy_id=None):
        self.calls.append((account_id, instrument_id, strategy_id))
        return self.snapshot


def make_buy_signal(
    *,
    signal_id: UUID | None = None,
    strategy_id: UUID | None = None,
    instrument_id: UUID | None = None,
) -> StrategySignal:
    return make_signal(
        signal_id=signal_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        action=SignalAction.BUY,
    )
