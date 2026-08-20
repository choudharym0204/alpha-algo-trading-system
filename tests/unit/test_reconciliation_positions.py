"""Phase 14 — position reconciliation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import DiscrepancyKind
from alpha_algo_reconciliation_engine.matching import MatchContext, reconcile_positions

from reconciliation_test_support import make_position_obs


def _ctx():
    return MatchContext(run_id=uuid4(), account_id=uuid4(), broker="PAPER", trading_mode="PAPER")


def test_exact_match():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, quantity=100, average_price="100")]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=100, average_price="100")]
    result = reconcile_positions(_ctx(), internal, broker)
    assert result.matched == 1
    assert result.discrepancies == ()


def test_missing_internal():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst)]
    result = reconcile_positions(_ctx(), internal, [])
    assert result.internal_only == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.INTERNAL_ONLY


def test_missing_broker():
    acc, inst = uuid4(), uuid4()
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst)]
    result = reconcile_positions(_ctx(), [], broker)
    assert result.broker_only == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.BROKER_ONLY


def test_quantity_mismatch_is_high():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, quantity=100)]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=80)]
    result = reconcile_positions(_ctx(), internal, broker)
    d = [x for x in result.discrepancies if x.kind == DiscrepancyKind.QUANTITY_MISMATCH]
    assert len(d) == 1
    assert d[0].severity.value == "HIGH"


def test_average_price_mismatch():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, average_price="100")]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, average_price="102")]
    kinds = {d.kind for d in reconcile_positions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.AVERAGE_PRICE_MISMATCH in kinds


def test_average_price_within_tolerance_matches():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, average_price="100.0000")]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, average_price="100.0001")]
    result = reconcile_positions(_ctx(), internal, broker)
    assert result.matched == 1


def test_broker_average_price_missing_is_not_a_mismatch():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, quantity=100, average_price="100")]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=100, average_price=None)]
    result = reconcile_positions(_ctx(), internal, broker)
    # Average price is not comparable when the broker omits it — quantity matches.
    assert result.matched == 1
    assert result.discrepancies == ()


def test_side_mismatch():
    acc, inst = uuid4(), uuid4()
    internal = [make_position_obs(account_id=acc, instrument_id=inst, side="LONG")]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, side="SHORT")]
    kinds = {d.kind for d in reconcile_positions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.SIDE_MISMATCH in kinds


def test_stale_broker_snapshot_is_not_hard_mismatch():
    acc, inst = uuid4(), uuid4()
    now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    internal = [make_position_obs(account_id=acc, instrument_id=inst, quantity=100)]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=80, observed_at=now - timedelta(minutes=30))]
    result = reconcile_positions(_ctx(), internal, broker, stale_seconds=600, now=now)
    kinds = {d.kind for d in result.discrepancies}
    assert DiscrepancyKind.STALE in kinds
    assert DiscrepancyKind.QUANTITY_MISMATCH not in kinds


def test_partial_broker_snapshot_reports_broker_only():
    acc = uuid4()
    internal = [
        make_position_obs(account_id=acc, instrument_id=uuid4()),
        make_position_obs(account_id=acc, instrument_id=uuid4()),
    ]
    broker = [make_position_obs(source="broker", account_id=acc, instrument_id=internal[0].instrument_id)]
    result = reconcile_positions(_ctx(), internal, broker)
    assert result.matched == 1
    assert result.internal_only == 1
