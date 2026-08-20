"""Phase 14 — funds/margin reconciliation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import DiscrepancyKind
from alpha_algo_reconciliation_engine.matching import MatchContext, reconcile_funds

from reconciliation_test_support import make_funds_obs


def _ctx():
    return MatchContext(run_id=uuid4(), account_id=uuid4(), broker="PAPER", trading_mode="PAPER")


def test_exact_match():
    internal = make_funds_obs(available_cash="1000000", available_margin="800000", used_margin="200000")
    broker = make_funds_obs(source="broker", available_cash="1000000", available_margin="800000", used_margin="200000")
    result = reconcile_funds(_ctx(), internal, broker)
    assert result.matched == 1
    assert result.discrepancies == ()


def test_rounding_tolerance_is_not_mismatch():
    internal = make_funds_obs(available_cash="1000000.00")
    broker = make_funds_obs(source="broker", available_cash="1000000.01")
    result = reconcile_funds(_ctx(), internal, broker)
    assert result.matched == 1


def test_cash_mismatch():
    internal = make_funds_obs(available_cash="1000000")
    broker = make_funds_obs(source="broker", available_cash="500000")
    kinds = {d.kind for d in reconcile_funds(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.CASH_MISMATCH in kinds


def test_margin_mismatch():
    internal = make_funds_obs(used_margin="200000")
    broker = make_funds_obs(source="broker", used_margin="300000")
    kinds = {d.kind for d in reconcile_funds(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.MARGIN_MISMATCH in kinds


def test_unavailable_funds_not_zero():
    internal = make_funds_obs(available_cash="1000000")
    broker = make_funds_obs(source="broker", available_cash=None)
    result = reconcile_funds(_ctx(), internal, broker)
    # None vs value is NOT treated as a zero-cash mismatch — it is a mismatch but never fabricated.
    kinds = {d.kind for d in result.discrepancies}
    assert DiscrepancyKind.CASH_MISMATCH in kinds
    # The broker value was never coerced to zero.
    assert result.discrepancies[0].broker_state.get("available_cash") is None


def test_stale_funds_is_not_hard_mismatch():
    now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    internal = make_funds_obs(available_cash="1000000")
    broker = make_funds_obs(source="broker", available_cash="500000", observed_at=now - timedelta(minutes=30))
    result = reconcile_funds(_ctx(), internal, broker, stale_seconds=600, now=now)
    kinds = {d.kind for d in result.discrepancies}
    assert DiscrepancyKind.STALE in kinds
    assert DiscrepancyKind.CASH_MISMATCH not in kinds


def test_broker_unavailable():
    result = reconcile_funds(_ctx(), make_funds_obs(), None)
    assert result.unavailable == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.UNKNOWN


def test_no_internal_funds_marks_unknown_not_zero():
    broker = make_funds_obs(source="broker", available_cash="1000000")
    result = reconcile_funds(_ctx(), None, broker)
    assert result.unknown == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.UNKNOWN
