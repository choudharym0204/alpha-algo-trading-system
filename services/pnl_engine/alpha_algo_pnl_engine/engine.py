"""P&L Engine (Phase 13).

Derives deterministic realized + unrealized P&L from authoritative execution /
position facts (Phase 11) + normalized reference prices (Phase 3/12), plus
explicitly-supplied costs. Broker-independent; no reconciliation (Phase 14), no
order submission, LIVE fail-closed.

Accounting method: **Weighted Average Cost** (long-only), consuming Phase 11's
authoritative average cost as the cost basis for realized P&L. Unrealized P&L is
mark-to-market and recalculable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Callable, Protocol
from uuid import UUID

from alpha_algo_pnl_engine.accounting import costs_total, net_pnl, realized_pnl_long
from alpha_algo_pnl_engine.aggregation import (
    account_aggregation,
    strategy_aggregation,
)
from alpha_algo_pnl_engine.contracts import (
    AggregatedPnl,
    PnlApplyStatus,
    PnlEvent,
    PnlEventType,
    PnlResult,
    PnlSnapshot,
    PnlStatus,
    PositionPnl,
    RealizedPnl,
    UnrealizedPnl,
)
from alpha_algo_pnl_engine.errors import (
    DuplicateExecutionError,
    PnlDataError,
    PnlError,
    PnlModeError,
    PnlOverCloseError,
    PnlPersistenceError,
    PnlValidationError,
)
from alpha_algo_pnl_engine.identity import event_content_hash
from alpha_algo_pnl_engine.metrics import PnlMetrics
from alpha_algo_pnl_engine.unrealized import mark_to_market

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


class PnlRepository(Protocol):
    """Durable P&L accounting store (PostgreSQL-backed)."""

    def save_event(self, *, event: PnlEvent) -> PnlEvent: ...

    def load_event(self, execution_id: str) -> PnlEvent | None: ...

    def list_events(
        self,
        *,
        account_id: UUID | None = None,
        strategy_run_id: UUID | None = None,
        instrument_id: UUID | None = None,
        position_id: UUID | None = None,
    ) -> list[PnlEvent]: ...

    def realized_pnl_for_position(self, *, position_id: UUID) -> Decimal: ...

    def save_snapshot(self, *, snapshot: PnlSnapshot) -> PnlSnapshot: ...

    def load_snapshot(
        self, *, account_id: UUID, trading_mode: str, snapshot_at: datetime
    ) -> PnlSnapshot | None: ...

    def load_latest_snapshot(
        self, *, account_id: UUID, trading_mode: str
    ) -> PnlSnapshot | None: ...


class PnlEngine:
    def __init__(
        self,
        *,
        repository: PnlRepository | None = None,
        metrics: PnlMetrics | None = None,
        global_halt_active: Callable[[], bool] | None = None,
        max_age_seconds: int | None = None,
        timezone=None,
    ) -> None:
        self._repository = repository
        self._metrics = metrics or PnlMetrics()
        self._global_halt_active = global_halt_active or (lambda: True)
        self._max_age_seconds = max_age_seconds
        self._timezone = timezone

    # ---------------------------------------------------------------- realized
    def record_fill(
        self,
        *,
        fill,
        position_before,
        costs: tuple = (),
    ) -> PnlResult:
        """Record the accounting effect of one normalized fill.

        ``position_before`` is the authoritative Phase-11 position **before**
        this fill (its ``average_price`` is the cost basis for a SELL).
        """
        self._validate(fill)
        started = perf_counter()
        try:
            if fill.side == "BUY":
                # No realized P&L on an opening/increasing fill (Phase 11 owns
                # cost-basis updates). Buy-leg cost netting is out of scope.
                self._metrics.record_latency(perf_counter() - started)
                return PnlResult(status=PnlApplyStatus.APPLIED)

            if position_before is None or position_before.quantity <= 0:
                raise PnlOverCloseError("SELL on a flat/unknown position")
            if int(fill.quantity) > position_before.quantity:
                raise PnlOverCloseError("SELL exceeds open long quantity")
            avg = position_before.average_price
            if avg is None:
                raise PnlDataError("cannot realize P&L without a cost basis")

            closed_qty = int(fill.quantity)
            gross = realized_pnl_long(
                sell_price=fill.price, average_cost=avg, closed_quantity=closed_qty
            )
            total_costs = costs_total(costs)
            net = net_pnl(gross=gross, costs=total_costs)

            event = self._build_event(
                fill=fill,
                position_id=position_before.position_id,
                event_type=PnlEventType.REALIZED_PNL,
                closed_qty=closed_qty,
                average_cost=avg,
                gross=gross,
                costs=total_costs,
                net=net,
            )

            try:
                persisted = self._repository.save_event(event=event)
            except DuplicateExecutionError:
                existing = self._repository.load_event(fill.execution_id)
                if existing is None:
                    raise PnlPersistenceError("duplicate but no existing event")
                if existing.content_hash != event.content_hash:
                    self._metrics.record_conflict()
                    return PnlResult(
                        status=PnlApplyStatus.CONFLICT,
                        conflict_original=existing,
                    )
                self._metrics.record_duplicate()
                return PnlResult(
                    status=PnlApplyStatus.DUPLICATE,
                    event=existing,
                    realized=self._to_realized(existing),
                )

            self._metrics.record_realized()
            if total_costs:
                self._metrics.record_cost()
            self._metrics.record_latency(perf_counter() - started)
            return PnlResult(
                status=PnlApplyStatus.APPLIED,
                event=persisted,
                realized=self._to_realized(persisted),
            )
        except PnlError:
            self._metrics.record_rejection()
            raise

    # -------------------------------------------------------------- unrealized
    def mark_to_market(
        self,
        *,
        position,
        price,
        now: datetime | None = None,
        max_age_seconds: int | None = None,
    ) -> UnrealizedPnl:
        started = perf_counter()
        result = mark_to_market(
            quantity=position.quantity,
            average_cost=position.average_price,
            position_id=position.position_id,
            instrument_id=position.instrument_id,
            price=price,
            now=now or datetime.now(tz=UTC),
            max_age_seconds=(
                max_age_seconds if max_age_seconds is not None else self._max_age_seconds
            ),
        )
        self._metrics.record_unrealized()
        if result.status == PnlStatus.DEGRADED:
            self._metrics.record_stale()
        elif result.status == PnlStatus.UNAVAILABLE:
            self._metrics.record_unavailable()
        self._metrics.record_latency(perf_counter() - started)
        return result

    # ------------------------------------------------------------- read models
    def position_pnl(
        self,
        *,
        position,
        price,
        realized_pnl: Decimal,
        now: datetime | None = None,
        max_age_seconds: int | None = None,
    ) -> PositionPnl:
        u = self.mark_to_market(
            position=position, price=price, now=now, max_age_seconds=max_age_seconds
        )
        market_value = (
            u.reference_price * Decimal(u.quantity)
            if u.reference_price is not None and u.quantity > 0
            else None
        )
        return PositionPnl(
            position_id=position.position_id,
            account_id=getattr(position, "account_id", None),
            strategy_run_id=position.strategy_run_id,
            instrument_id=position.instrument_id,
            trading_mode=position.trading_mode,
            quantity=position.quantity,
            average_cost=position.average_price,
            reference_price=u.reference_price,
            market_value=market_value,
            unrealized_pnl=u.unrealized_pnl,
            realized_pnl=realized_pnl,
            status=u.status,
        )

    def strategy_pnl(self, events) -> tuple[AggregatedPnl, ...]:
        return strategy_aggregation(events)

    def account_pnl(self, events) -> tuple[AggregatedPnl, ...]:
        return account_aggregation(events)

    # --------------------------------------------------------------- snapshots
    def snapshot(
        self,
        *,
        account_id: UUID,
        trading_mode: str,
        snapshot_at: datetime,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal | None,
        costs: Decimal,
        position_count: int,
        status: PnlStatus,
    ) -> PnlSnapshot:
        if self._repository is None:
            raise PnlPersistenceError("no P&L repository configured")
        self._guard_mode(trading_mode)
        gross = realized_pnl + (unrealized_pnl or Decimal("0"))
        net = (realized_pnl - costs) + (unrealized_pnl or Decimal("0"))
        snap = PnlSnapshot(
            snapshot_id=None,
            account_id=account_id,
            trading_mode=trading_mode.upper(),
            snapshot_at=snapshot_at,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            gross_pnl=gross,
            costs=costs,
            net_pnl=net,
            position_count=position_count,
            status=status,
        )
        try:
            persisted = self._repository.save_snapshot(snapshot=snap)
        except DuplicateExecutionError:
            existing = self._repository.load_snapshot(
                account_id=account_id, trading_mode=trading_mode, snapshot_at=snapshot_at
            )
            if existing is None:
                raise PnlPersistenceError("snapshot duplicate but none found")
            return existing
        self._metrics.record_snapshot_write()
        return persisted

    def get_latest_snapshot(self, *, account_id: UUID, trading_mode: str) -> PnlSnapshot | None:
        if self._repository is None:
            return None
        return self._repository.load_latest_snapshot(
            account_id=account_id, trading_mode=trading_mode
        )

    # --------------------------------------------------------------- internals
    def _validate(self, fill) -> None:
        self._guard_mode(fill.trading_mode)
        if self._global_halt_active():
            raise PnlValidationError("global trading halt is active; P&L refused")

    def _guard_mode(self, trading_mode: str) -> None:
        mode = (trading_mode or "").upper()
        if mode == "LIVE":
            raise PnlModeError("LIVE trading is disabled (fail-closed)")
        if mode not in _ALLOWED_MODES:
            raise PnlModeError(f"unknown trading mode: {trading_mode}")

    def _build_event(
        self,
        *,
        fill,
        position_id,
        event_type,
        closed_qty,
        average_cost,
        gross,
        costs,
        net,
    ) -> PnlEvent:
        content_hash = event_content_hash(
            execution_id=fill.execution_id,
            event_type=event_type.value,
            account_id=fill.account_id,
            strategy_run_id=fill.strategy_run_id,
            instrument_id=fill.instrument_id,
            trading_mode=fill.trading_mode,
            side=fill.side,
            quantity=closed_qty,
            price=str(fill.price),
            average_cost=str(average_cost),
            gross_pnl=str(gross),
            costs=str(costs),
            net_pnl=str(net),
            occurred_at=fill.occurred_at,
        )
        return PnlEvent(
            id=None,
            execution_id=fill.execution_id,
            event_type=event_type,
            account_id=fill.account_id,
            strategy_run_id=fill.strategy_run_id,
            instrument_id=fill.instrument_id,
            position_id=position_id,
            trading_mode=fill.trading_mode.upper(),
            side=fill.side,
            quantity=closed_qty,
            price=fill.price,
            average_cost=average_cost,
            gross_pnl=gross,
            costs=costs,
            net_pnl=net,
            occurred_at=fill.occurred_at,
            content_hash=content_hash,
        )

    def _to_realized(self, event: PnlEvent) -> RealizedPnl:
        return RealizedPnl(
            execution_id=event.execution_id,
            account_id=event.account_id,
            strategy_run_id=event.strategy_run_id,
            instrument_id=event.instrument_id,
            trading_mode=event.trading_mode,
            closed_quantity=event.quantity,
            sell_price=event.price,
            average_cost=event.average_cost,
            gross_pnl=event.gross_pnl,
            costs=event.costs,
            net_pnl=event.net_pnl,
            occurred_at=event.occurred_at,
        )
