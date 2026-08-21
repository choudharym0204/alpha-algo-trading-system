"""Pure reconciliation matching + classification (Phase 14).

Comparison is deterministic and key-based (strongest identity first). Stale /
unavailable observations never become hard financial mismatches. Only
non-MATCH outcomes are materialized as ``Discrepancy`` evidence; matches are
counted. Provider-specific logic lives in the broker adapter, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from alpha_algo_reconciliation_engine.contracts import (
    Discrepancy,
    DiscrepancyKind,
    EntityType,
    ExecutionObservation,
    FundsObservation,
    OrderObservation,
    PositionObservation,
    ResolutionStatus,
    Severity,
)
from alpha_algo_reconciliation_engine.identity import (
    compute_discrepancy_key,
    discrepancy_content_hash,
)
from alpha_algo_reconciliation_engine.tolerance import Tolerance, within


@dataclass(frozen=True)
class MatchContext:
    run_id: UUID
    account_id: UUID
    broker: str
    trading_mode: str


@dataclass(frozen=True)
class ComparisonResult:
    discrepancies: tuple[Discrepancy, ...]
    matched: int = 0
    internal_only: int = 0
    broker_only: int = 0
    unknown: int = 0
    unavailable: int = 0
    skipped: int = 0

    @property
    def mismatched(self) -> int:
        return len(self.discrepancies)


def _severity(kind: DiscrepancyKind, entity_type: EntityType) -> Severity:
    if kind == DiscrepancyKind.ROUNDING_DIFFERENCE:
        return Severity.INFO
    if kind in (DiscrepancyKind.UNKNOWN, DiscrepancyKind.STALE):
        return Severity.WARNING
    if kind == DiscrepancyKind.INTERNAL_ONLY:
        return Severity.WARNING
    if kind == DiscrepancyKind.BROKER_ONLY and entity_type == EntityType.EXECUTION:
        return Severity.CRITICAL  # unexpected broker fill
    if kind == DiscrepancyKind.BROKER_ONLY:
        return Severity.WARNING  # expected provider timing lag
    if kind == DiscrepancyKind.DUPLICATE_EXECUTION:
        return Severity.HIGH
    if kind == DiscrepancyKind.CONFLICT:
        return Severity.HIGH
    if kind in (DiscrepancyKind.CASH_MISMATCH, DiscrepancyKind.MARGIN_MISMATCH):
        return Severity.WARNING
    # quantity / side / average / status / price / fee / account / instrument / order-link
    return Severity.HIGH


def _discrepancy(
    ctx: MatchContext,
    *,
    entity_type: EntityType,
    entity_id: str,
    kind: DiscrepancyKind,
    internal_state: dict,
    broker_state: dict,
    observed_at: datetime | None,
) -> Discrepancy:
    key = compute_discrepancy_key(
        account_id=ctx.account_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        kind=kind.value,
    )
    content_hash = discrepancy_content_hash(
        internal_state=internal_state, broker_state=broker_state, observed_at=observed_at
    )
    return Discrepancy(
        id=None,
        discrepancy_key=key,
        run_id=ctx.run_id,
        account_id=ctx.account_id,
        broker=ctx.broker,
        trading_mode=ctx.trading_mode,
        entity_type=entity_type,
        entity_id=entity_id,
        kind=kind,
        severity=_severity(kind, entity_type),
        internal_state=internal_state,
        broker_state=broker_state,
        resolution_status=ResolutionStatus.OPEN,
        content_hash=content_hash,
        observed_at=observed_at,
    )


# --------------------------------------------------------------------- orders
def order_match_key(obs: OrderObservation) -> str | None:
    return obs.broker_order_id or obs.client_order_id


def _compare_order_fields(internal: OrderObservation, broker: OrderObservation) -> list[DiscrepancyKind]:
    kinds: list[DiscrepancyKind] = []
    if internal.status is not None and broker.status is not None and internal.status != broker.status:
        kinds.append(DiscrepancyKind.STATUS_MISMATCH)
    if internal.quantity is not None and broker.quantity is not None and internal.quantity != broker.quantity:
        kinds.append(DiscrepancyKind.QUANTITY_MISMATCH)
    if internal.side is not None and broker.side is not None and internal.side != broker.side:
        kinds.append(DiscrepancyKind.SIDE_MISMATCH)
    if internal.order_type is not None and broker.order_type is not None and internal.order_type != broker.order_type:
        kinds.append(DiscrepancyKind.ORDER_TYPE_MISMATCH)
    if internal.instrument_id is not None and broker.instrument_id is not None and internal.instrument_id != broker.instrument_id:
        kinds.append(DiscrepancyKind.INSTRUMENT_MISMATCH)
    if internal.account_id is not None and broker.account_id is not None and internal.account_id != broker.account_id:
        kinds.append(DiscrepancyKind.ACCOUNT_MISMATCH)
    return kinds


def reconcile_orders(ctx: MatchContext, internal: list[OrderObservation], broker: list[OrderObservation], tolerance: Tolerance | None = None) -> ComparisonResult:
    broker_index: dict[str, list[OrderObservation]] = {}
    for o in broker:
        key = order_match_key(o)
        if key is not None:
            broker_index.setdefault(key, []).append(o)

    discrepancies: list[Discrepancy] = []
    consumed: set[int] = set()
    matched = internal_only = broker_only = 0

    # Duplicate / conflicting broker orders (same key).
    for key, group in broker_index.items():
        if len(group) > 1:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.ORDER, entity_id=key,
                    kind=DiscrepancyKind.CONFLICT,
                    internal_state={}, broker_state={"duplicate_count": len(group)},
                    observed_at=group[0].observed_at,
                )
            )

    for i, internal_obs in enumerate(internal):
        key = order_match_key(internal_obs)
        counterpart = None
        cidx = None
        if key is not None and key in broker_index:
            for j, bo in enumerate(broker_index[key]):
                if j not in consumed:
                    counterpart, cidx = bo, j
                    break
        if counterpart is None:
            internal_only += 1
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.ORDER, entity_id=key or str(i),
                    kind=DiscrepancyKind.INTERNAL_ONLY,
                    internal_state=_order_state(internal_obs),
                    broker_state={},
                    observed_at=internal_obs.observed_at,
                )
            )
            continue
        consumed.add(cidx)
        kinds = _compare_order_fields(internal_obs, counterpart)
        if not kinds:
            matched += 1
            continue
        for kind in kinds:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.ORDER, entity_id=key or str(i),
                    kind=kind,
                    internal_state=_order_state(internal_obs),
                    broker_state=_order_state(counterpart),
                    observed_at=counterpart.observed_at,
                )
            )

    # Broker-only: unconsumed broker orders.
    for key, group in broker_index.items():
        for j, bo in enumerate(group):
            if j not in consumed:
                broker_only += 1
                discrepancies.append(
                    _discrepancy(
                        ctx, entity_type=EntityType.ORDER, entity_id=key or bo.client_order_id or "",
                        kind=DiscrepancyKind.BROKER_ONLY,
                        internal_state={},
                        broker_state=_order_state(bo),
                        observed_at=bo.observed_at,
                    )
                )

    return ComparisonResult(discrepancies=tuple(discrepancies), matched=matched, internal_only=internal_only, broker_only=broker_only)


def _order_state(obs: OrderObservation) -> dict:
    return {
        "broker_order_id": obs.broker_order_id,
        "client_order_id": obs.client_order_id,
        "status": obs.status,
        "quantity": obs.quantity,
        "side": obs.side,
        "order_type": obs.order_type,
        "instrument_id": str(obs.instrument_id) if obs.instrument_id else None,
        "account_id": str(obs.account_id) if obs.account_id else None,
    }


# ---------------------------------------------------------------- executions
def execution_match_key(obs: ExecutionObservation) -> str | None:
    return obs.broker_execution_id or obs.execution_id or obs.broker_order_id


def reconcile_executions(ctx: MatchContext, internal: list[ExecutionObservation], broker: list[ExecutionObservation], tolerance: Tolerance | None = None) -> ComparisonResult:
    tol = tolerance or Tolerance()
    broker_index: dict[str, list[ExecutionObservation]] = {}
    for e in broker:
        key = execution_match_key(e)
        if key is not None:
            broker_index.setdefault(key, []).append(e)

    discrepancies: list[Discrepancy] = []
    consumed: set[int] = set()
    matched = internal_only = broker_only = 0

    for key, group in broker_index.items():
        if len(group) > 1:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.EXECUTION, entity_id=key,
                    kind=DiscrepancyKind.DUPLICATE_EXECUTION,
                    internal_state={}, broker_state={"duplicate_count": len(group)},
                    observed_at=group[0].observed_at,
                )
            )

    for i, internal_obs in enumerate(internal):
        key = execution_match_key(internal_obs)
        counterpart = None
        cidx = None
        if key is not None and key in broker_index:
            for j, be in enumerate(broker_index[key]):
                if j not in consumed:
                    counterpart, cidx = be, j
                    break
        if counterpart is None:
            internal_only += 1
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.EXECUTION, entity_id=key or str(i),
                    kind=DiscrepancyKind.INTERNAL_ONLY,
                    internal_state=_exec_state(internal_obs), broker_state={},
                    observed_at=internal_obs.observed_at,
                )
            )
            continue
        consumed.add(cidx)
        kinds = _compare_execution_fields(internal_obs, counterpart, tol)
        if not kinds:
            matched += 1
            continue
        for kind in kinds:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.EXECUTION, entity_id=key or str(i),
                    kind=kind,
                    internal_state=_exec_state(internal_obs),
                    broker_state=_exec_state(counterpart),
                    observed_at=counterpart.observed_at,
                )
            )

    for key, group in broker_index.items():
        for j, be in enumerate(group):
            if j not in consumed:
                broker_only += 1
                discrepancies.append(
                    _discrepancy(
                        ctx, entity_type=EntityType.EXECUTION, entity_id=key or "",
                        kind=DiscrepancyKind.BROKER_ONLY,
                        internal_state={}, broker_state=_exec_state(be),
                        observed_at=be.observed_at,
                    )
                )

    return ComparisonResult(discrepancies=tuple(discrepancies), matched=matched, internal_only=internal_only, broker_only=broker_only)


def _compare_execution_fields(internal: ExecutionObservation, broker: ExecutionObservation, tol: Tolerance) -> list[DiscrepancyKind]:
    kinds: list[DiscrepancyKind] = []
    if internal.quantity is not None and broker.quantity is not None and internal.quantity != broker.quantity:
        kinds.append(DiscrepancyKind.QUANTITY_MISMATCH)
    if internal.price is not None and broker.price is not None and not within(internal.price, broker.price, tol.price_epsilon):
        kinds.append(DiscrepancyKind.PRICE_MISMATCH)
    if internal.fees is not None and broker.fees is not None and not within(internal.fees, broker.fees, tol.fee_epsilon):
        kinds.append(DiscrepancyKind.FEE_MISMATCH)
    if internal.order_id is not None and broker.order_id is not None and internal.order_id != broker.order_id:
        kinds.append(DiscrepancyKind.ORDER_LINK_MISMATCH)
    if internal.side is not None and broker.side is not None and internal.side != broker.side:
        kinds.append(DiscrepancyKind.SIDE_MISMATCH)
    return kinds


def _exec_state(obs: ExecutionObservation) -> dict:
    return {
        "broker_execution_id": obs.broker_execution_id,
        "execution_id": obs.execution_id,
        "order_id": str(obs.order_id) if obs.order_id else None,
        "quantity": str(obs.quantity) if obs.quantity is not None else None,
        "price": str(obs.price) if obs.price is not None else None,
        "fees": str(obs.fees) if obs.fees is not None else None,
        "side": obs.side,
        "status": obs.status,
    }


# ---------------------------------------------------------------- positions
def position_match_key(obs: PositionObservation) -> str:
    return f"{obs.account_id}:{obs.instrument_id}"


def reconcile_positions(ctx: MatchContext, internal: list[PositionObservation], broker: list[PositionObservation], tolerance: Tolerance | None = None, *, stale_seconds: int | None = None, now: datetime | None = None) -> ComparisonResult:
    tol = tolerance or Tolerance()
    broker_index = {position_match_key(o): o for o in broker}

    discrepancies: list[Discrepancy] = []
    consumed: set[str] = set()
    matched = internal_only = broker_only = unknown = 0

    for internal_obs in internal:
        key = position_match_key(internal_obs)
        counterpart = broker_index.get(key)
        if counterpart is None:
            internal_only += 1
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.POSITION, entity_id=key,
                    kind=DiscrepancyKind.INTERNAL_ONLY,
                    internal_state=_position_state(internal_obs), broker_state={},
                    observed_at=internal_obs.observed_at,
                )
            )
            continue
        consumed.add(key)
        # Stale broker observation → UNKNOWN, not a hard mismatch.
        if counterpart.observed_at is not None and now is not None and stale_seconds is not None:
            if (now - counterpart.observed_at).total_seconds() > stale_seconds:
                unknown += 1
                discrepancies.append(
                    _discrepancy(
                        ctx, entity_type=EntityType.POSITION, entity_id=key,
                        kind=DiscrepancyKind.STALE,
                        internal_state=_position_state(internal_obs),
                        broker_state=_position_state(counterpart),
                        observed_at=counterpart.observed_at,
                    )
                )
                continue
        kinds = _compare_position_fields(internal_obs, counterpart, tol)
        if not kinds:
            matched += 1
            continue
        for kind in kinds:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.POSITION, entity_id=key,
                    kind=kind,
                    internal_state=_position_state(internal_obs),
                    broker_state=_position_state(counterpart),
                    observed_at=counterpart.observed_at,
                )
            )

    for key, bo in broker_index.items():
        if key not in consumed:
            broker_only += 1
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.POSITION, entity_id=key,
                    kind=DiscrepancyKind.BROKER_ONLY,
                    internal_state={}, broker_state=_position_state(bo),
                    observed_at=bo.observed_at,
                )
            )

    return ComparisonResult(discrepancies=tuple(discrepancies), matched=matched, internal_only=internal_only, broker_only=broker_only, unknown=unknown)


def _compare_position_fields(internal: PositionObservation, broker: PositionObservation, tol: Tolerance) -> list[DiscrepancyKind]:
    kinds: list[DiscrepancyKind] = []
    if internal.quantity != broker.quantity:
        kinds.append(DiscrepancyKind.QUANTITY_MISMATCH)
    if internal.side != broker.side:
        kinds.append(DiscrepancyKind.SIDE_MISMATCH)
    # Average price is only comparable when both sides report it (a broker that
    # omits average price is a data gap, not a hard financial mismatch).
    if internal.average_price is not None and broker.average_price is not None:
        if not within(internal.average_price, broker.average_price, tol.price_epsilon):
            kinds.append(DiscrepancyKind.AVERAGE_PRICE_MISMATCH)
    return kinds


def _position_state(obs: PositionObservation) -> dict:
    return {
        "account_id": str(obs.account_id) if obs.account_id else None,
        "instrument_id": str(obs.instrument_id) if obs.instrument_id else None,
        "quantity": obs.quantity,
        "side": obs.side,
        "average_price": str(obs.average_price) if obs.average_price is not None else None,
    }


# ---------------------------------------------------------------------- funds
def reconcile_funds(ctx: MatchContext, internal: FundsObservation | None, broker: FundsObservation | None, tolerance: Tolerance | None = None, *, stale_seconds: int | None = None, now: datetime | None = None) -> ComparisonResult:
    tol = tolerance or Tolerance()
    discrepancies: list[Discrepancy] = []
    matched = unknown = unavailable = 0

    if broker is None:
        unavailable += 1
        discrepancies.append(
            _discrepancy(
                ctx, entity_type=EntityType.FUNDS, entity_id=str(ctx.account_id),
                kind=DiscrepancyKind.UNKNOWN,
                internal_state=_funds_state(internal) if internal else {},
                broker_state={},
                observed_at=None,
            )
        )
        return ComparisonResult(discrepancies=tuple(discrepancies), unavailable=unavailable)

    if internal is None:
        # No authoritative internal funds: do not invent one; mark unknown.
        unknown += 1
        discrepancies.append(
            _discrepancy(
                ctx, entity_type=EntityType.FUNDS, entity_id=str(ctx.account_id),
                kind=DiscrepancyKind.UNKNOWN,
                internal_state={}, broker_state=_funds_state(broker),
                observed_at=broker.observed_at,
            )
        )
        return ComparisonResult(discrepancies=tuple(discrepancies), unknown=unknown)

    if broker.observed_at is not None and now is not None and stale_seconds is not None:
        if (now - broker.observed_at).total_seconds() > stale_seconds:
            unknown += 1
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.FUNDS, entity_id=str(ctx.account_id),
                    kind=DiscrepancyKind.STALE,
                    internal_state=_funds_state(internal), broker_state=_funds_state(broker),
                    observed_at=broker.observed_at,
                )
            )
            return ComparisonResult(discrepancies=tuple(discrepancies), unknown=unknown)

    kinds: list[DiscrepancyKind] = []
    if not within(internal.available_cash, broker.available_cash, tol.funds_epsilon):
        kinds.append(DiscrepancyKind.CASH_MISMATCH)
    if not within(internal.available_margin, broker.available_margin, tol.funds_epsilon):
        kinds.append(DiscrepancyKind.MARGIN_MISMATCH)
    if not within(internal.used_margin, broker.used_margin, tol.funds_epsilon):
        kinds.append(DiscrepancyKind.MARGIN_MISMATCH)

    if not kinds:
        matched += 1
    else:
        for kind in kinds:
            discrepancies.append(
                _discrepancy(
                    ctx, entity_type=EntityType.FUNDS, entity_id=str(ctx.account_id),
                    kind=kind,
                    internal_state=_funds_state(internal), broker_state=_funds_state(broker),
                    observed_at=broker.observed_at,
                )
            )

    return ComparisonResult(discrepancies=tuple(discrepancies), matched=matched)


def _funds_state(obs: FundsObservation) -> dict:
    return {
        "account_id": str(obs.account_id) if obs.account_id else None,
        "available_cash": str(obs.available_cash) if obs.available_cash is not None else None,
        "available_margin": str(obs.available_margin) if obs.available_margin is not None else None,
        "used_margin": str(obs.used_margin) if obs.used_margin is not None else None,
        "currency": obs.currency,
    }
