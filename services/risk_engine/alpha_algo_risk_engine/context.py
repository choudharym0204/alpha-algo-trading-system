"""Build + validate ``RiskEvaluationContext`` from a ``RiskSnapshot`` (Phase 6).

The builder derives the flat rule context from the immutable snapshot plus the
signal and the (minimal) order intent. Missing authoritative state fails closed
(``RiskContextUnavailable``). The builder also cross-checks that the snapshot is
*for* the requested account/instrument and trading mode, so a mis-keyed provider
cannot silently produce a risk decision against the wrong identity. The validator
catches internally-inconsistent (malformed/ambiguous) values before the rule
engine runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import StrategySignal
from alpha_algo_risk_engine.engine import RiskEvaluationContext, RiskTradingMode
from alpha_algo_risk_engine.snapshot import RiskSnapshot


@dataclass(frozen=True)
class RiskOrderIntent:
    """Minimal order intent the risk engine evaluates (full OMS is Phase 8)."""

    quantity: Decimal | None = None
    account_id: UUID | None = None
    order_type: str = "MARKET"
    metadata: dict[str, object] = field(default_factory=dict)


class RiskContextError(Exception):
    """Base error for risk-context construction."""


class RiskContextUnavailable(RiskContextError):
    """Authoritative state is unavailable, stale, or mismatched (fail closed)."""


def _mode(value: str) -> RiskTradingMode:
    try:
        return RiskTradingMode(value.upper())
    except ValueError:
        return RiskTradingMode.LIVE  # unknown → LIVE → fail closed


def _action_sign(action_value: str) -> Decimal:
    """BUY → +1, SELL/EXIT → -1, HOLD → 0. Unknown action fails closed."""
    if action_value == "BUY":
        return Decimal("1")
    if action_value in ("SELL", "EXIT"):
        return Decimal("-1")
    if action_value == "HOLD":
        return Decimal("0")
    raise RiskContextUnavailable(f"unsupported signal action: {action_value}")


class RiskContextBuilder:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def build(
        self,
        signal: StrategySignal,
        intent: RiskOrderIntent | None,
        snapshot: RiskSnapshot,
        *,
        trading_mode: str = "PAPER",
        retry_count: int = 0,
    ) -> RiskEvaluationContext:
        if not snapshot.state_available:
            raise RiskContextUnavailable("authoritative risk state is unavailable")
        now = self._clock()
        if snapshot.is_stale(now):
            raise RiskContextUnavailable("risk snapshot is stale")

        # Trading-mode single-source: the requested mode must match the snapshot.
        boundary_mode = _mode(trading_mode)
        snapshot_mode = _mode(snapshot.trading_mode)
        if snapshot_mode != boundary_mode:
            raise RiskContextUnavailable(
                f"snapshot trading mode {snapshot.trading_mode!r} does not match "
                f"requested mode {trading_mode!r}"
            )

        # Identity cross-checks: the snapshot must be for the requested parties.
        if (
            intent is not None
            and intent.account_id is not None
            and snapshot.account.account_id is not None
            and intent.account_id != snapshot.account.account_id
        ):
            raise RiskContextUnavailable("snapshot account does not match intent account")
        if (
            snapshot.market.instrument_id is not None
            and snapshot.market.instrument_id != signal.instrument_id
        ):
            raise RiskContextUnavailable("snapshot instrument does not match signal instrument")

        acc = snapshot.account
        mkt = snapshot.market
        pos = snapshot.positions
        lim = snapshot.limits
        frq = snapshot.frequency

        action = signal.action.value
        sign = _action_sign(action)
        quantity = intent.quantity if intent is not None else None
        if action == "HOLD":
            # A HOLD carries no order quantity.
            quantity = None

        # Base projected position (before this intent) = authoritative projected
        # value, else fall back to filled + reserved (pending) quantity.
        base_position = pos.projected_position_quantity
        if base_position is None and pos.position_quantity is not None:
            base_position = pos.position_quantity + (pos.reserved_quantity or Decimal("0"))

        # Projected position including this intent.
        projected = None
        if base_position is not None:
            projected = base_position + (sign * quantity if quantity is not None else Decimal("0"))

        # Projected exposure (before this intent) = authoritative exposure, then
        # add |intent| * price. A present intent with a missing price fails
        # closed (None) rather than silently ignoring the intent's exposure.
        projected_exposure = None
        if pos.exposure is not None:
            if quantity is not None:
                if mkt.current_price is None:
                    projected_exposure = None  # fail closed
                else:
                    projected_exposure = pos.exposure + abs(quantity) * mkt.current_price
            else:
                projected_exposure = pos.exposure

        # Required margin = |quantity| * price (conservative full-notional).
        required_margin = None
        if quantity is not None and mkt.current_price is not None:
            required_margin = abs(quantity) * mkt.current_price

        # Drawdown derived from equity vs high-water mark when not explicit,
        # clamped at zero so a new equity high is not a negative drawdown.
        current_drawdown = acc.current_drawdown
        if (
            current_drawdown is None
            and acc.equity is not None
            and acc.high_water_mark is not None
            and acc.high_water_mark > 0
        ):
            current_drawdown = max(
                Decimal("0"), (acc.high_water_mark - acc.equity) / acc.high_water_mark
            )

        return RiskEvaluationContext(
            trading_mode=boundary_mode,
            live_trading_enabled=snapshot.live_trading_enabled,
            global_halt_active=snapshot.global_halt_active,
            broker_connected=mkt.broker_connected,
            market_data_fresh=mkt.market_data_fresh,
            market_session_open=mkt.market_session_open,
            instrument_allowed=mkt.instrument_allowed,
            duplicate_signal=snapshot.duplicate_signal,
            order_quantity=quantity,
            max_order_quantity=lim.max_order_quantity,
            projected_position_quantity=projected,
            max_position_quantity=lim.max_position_quantity,
            projected_exposure=projected_exposure,
            max_exposure=lim.max_exposure,
            daily_realized_pnl=acc.daily_realized_pnl,
            max_daily_loss=lim.max_daily_loss,
            strategy_realized_pnl=acc.strategy_realized_pnl,
            max_strategy_loss=lim.max_strategy_loss,
            required_margin=required_margin,
            available_margin=acc.available_margin,
            open_positions_count=pos.open_positions_count,
            max_open_positions=lim.max_open_positions,
            equity_value=acc.equity,
            high_water_mark=acc.high_water_mark,
            current_drawdown=current_drawdown,
            max_drawdown=lim.max_drawdown,
            reference_price=mkt.reference_price,
            current_price=mkt.current_price,
            max_price_deviation=lim.max_price_deviation,
            recent_order_count=frq.recent_order_count,
            max_orders_per_window=lim.max_orders_per_window,
            order_window_seconds=lim.order_window_seconds,
            account_max_order_quantity=lim.account_max_order_quantity,
            account_max_positions=lim.account_max_positions,
            account_max_exposure=lim.account_max_exposure,
            account_max_loss=lim.account_max_loss,
            account_max_order_rate=lim.account_max_order_rate,
            account_daily_realized_pnl=acc.daily_realized_pnl,
            pending_execution_count=pos.pending_order_count,
            max_unresolved_executions=lim.max_unresolved_executions,
            retry_count=retry_count,
            max_retries_per_signal=lim.max_retries_per_signal,
            reserved_quantity=pos.reserved_quantity,
            open_order_quantity=pos.reserved_quantity,
            metadata=snapshot.metadata,
        )


class RiskContextValidator:
    """Cross-field consistency checks (fail closed on malformed/ambiguous state)."""

    def validate(self, context: RiskEvaluationContext) -> list[str]:
        problems: list[str] = []
        for name in ("equity_value", "high_water_mark", "current_price", "reference_price"):
            value = getattr(context, name)
            if value is not None and value < 0:
                problems.append(f"{name} must be non-negative")
        for name in ("order_quantity", "reserved_quantity", "open_order_quantity"):
            value = getattr(context, name)
            if value is not None and value < 0:
                problems.append(f"{name} must be non-negative")
        return problems
