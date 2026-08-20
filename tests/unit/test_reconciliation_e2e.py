"""Phase 14 — end-to-end test (broker observation → reconcile → read-back)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_broker_integration.contracts import (
    BrokerFundsSnapshot,
    BrokerPositionSnapshot,
    TradingMode,
)
from alpha_algo_position_engine.contracts import (
    PositionSide,
    PositionSnapshot,
    PositionStatus,
)
from alpha_algo_reconciliation_engine.adapters import (
    funds_observation_from_broker,
    funds_observation_from_internal,
    position_observation_from_broker,
    position_observation_from_internal,
)
from alpha_algo_reconciliation_engine.contracts import (
    DiscrepancyKind,
    ReconciliationInputs,
    ReconciliationScope,
    RunStatus,
)
from alpha_algo_reconciliation_engine.engine import ReconciliationEngine

from reconciliation_test_support import InMemoryReconciliationRepository


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_broker_position_and_funds_reconcile_end_to_end():
    repo = InMemoryReconciliationRepository()
    engine = ReconciliationEngine(repository=repo, global_halt_active=lambda: False)
    acc, inst_a, inst_b, strat = uuid4(), uuid4(), uuid4(), uuid4()

    # Internal authority: one position (inst A, 100 @ 100).
    internal_snap = PositionSnapshot(
        position_id=uuid4(), account_id=acc, instrument_id=inst_a, strategy_run_id=strat,
        trading_mode="PAPER", side=PositionSide.LONG, quantity=100,
        average_price=Decimal("100.0000"), status=PositionStatus.OPEN,
        opened_at=_t(), closed_at=None, last_execution_id=None,
    )

    # Broker observation: inst A matches, inst B is broker-only.
    broker_positions = [
        BrokerPositionSnapshot(broker_account_id=acc, instrument_id=inst_a, trading_mode=TradingMode.PAPER, quantity=Decimal("100"), average_price=Decimal("100.0000"), captured_at=_t()),
        BrokerPositionSnapshot(broker_account_id=acc, instrument_id=inst_b, trading_mode=TradingMode.PAPER, quantity=Decimal("50"), average_price=Decimal("80.0000"), captured_at=_t()),
    ]

    broker_funds = BrokerFundsSnapshot(broker_account_id=acc, available_cash=Decimal("1000000"), available_margin=Decimal("800000"), used_margin=Decimal("200000"), currency="INR", captured_at=_t())

    inputs = ReconciliationInputs(
        positions_internal=(position_observation_from_internal(internal_snap),),
        positions_broker=tuple(position_observation_from_broker(p) for p in broker_positions),
        funds_internal=funds_observation_from_internal(type("F", (), {"account_id": acc, "available_cash": Decimal("1000000"), "available_margin": Decimal("800000"), "used_margin": Decimal("200000"), "currency": "INR"})()),
        funds_broker=funds_observation_from_broker(broker_funds),
    )

    scope = ReconciliationScope(account_id=acc, broker="PAPER", trading_mode="PAPER", domains=frozenset({"POSITIONS", "FUNDS"}))
    result = engine.run(scope=scope, inputs=inputs)

    assert result.status == RunStatus.COMPLETED
    # 1 position match + 1 broker-only position + 1 funds match.
    assert result.run.matched == 2
    broker_only = [d for d in result.discrepancies if d.kind == DiscrepancyKind.BROKER_ONLY]
    assert len(broker_only) == 1
    assert broker_only[0].entity_type.value == "POSITION"

    # Read-back: discrepancies are durable and account-scoped.
    read_back = engine.list_discrepancies(account_id=acc)
    assert len(read_back) == 1
    assert read_back[0].broker_state["quantity"] == 50


def test_internal_funds_vs_broker_funds_through_adapters():
    acc = uuid4()
    internal = funds_observation_from_internal(type("F", (), {"account_id": acc, "available_cash": Decimal("1000000"), "available_margin": Decimal("800000"), "used_margin": Decimal("200000"), "currency": "INR"})())
    broker = funds_observation_from_broker(
        BrokerFundsSnapshot(broker_account_id=acc, available_cash=Decimal("1000000"), available_margin=Decimal("800000"), used_margin=Decimal("200000"), currency="INR", captured_at=_t())
    )
    assert internal.available_cash == broker.available_cash
    assert internal.used_margin == Decimal("200000")
