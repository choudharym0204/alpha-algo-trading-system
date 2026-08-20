from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from alpha_algo_broker_adapters import OrderSide, OrderType
from alpha_algo_broker_integration.contracts import BrokerFundsSnapshot
from alpha_algo_paper_trading import PaperBrokerAdapter
from alpha_algo_paper_runtime import PaperTradingService
from alpha_algo_position_engine import PositionEngine, PositionFill
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

from paper_test_support import (
    FIXED_NOW,
    InMemoryPaperRepository,
    connect_broker,
    make_account,
    make_reference,
)
from position_test_support import InMemoryPositionRepository
from reconciliation_test_support import InMemoryReconciliationRepository


def _run(coro):
    return asyncio.run(coro)


def _service(account, inst, last="100", repository=None):
    refs = {inst: make_reference(inst, last=last)}
    broker = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices=refs)
    connect_broker(broker, account.account_id)
    svc = PaperTradingService(
        account=account, broker=broker, reference_prices=refs,
        clock=lambda: FIXED_NOW, repository=repository,
    )
    return svc


def _to_fill(outcome, account_id, strategy_run_id) -> PositionFill:
    return PositionFill(
        execution_id=f"exec-{outcome.order_id}",
        order_id=outcome.order_id,
        account_id=account_id,
        instrument_id=outcome.instrument_id,
        strategy_run_id=strategy_run_id,
        trading_mode="PAPER",
        side=outcome.side.value,
        quantity=Decimal(outcome.quantity),
        price=outcome.fill_price,
        occurred_at=outcome.occurred_at,
    )


def test_buy_hold_sell_close_lifecycle() -> None:
    inst = uuid4()
    account = make_account(starting_capital="100000")
    svc = _service(account, inst, last="100")

    buy = _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    assert buy.accepted is True
    assert buy.fill_price == Decimal("100")
    assert buy.net_cash == Decimal("-1000")
    assert svc.funds.available_cash == Decimal("99000")

    # HOLD: one open position of 10.
    positions = _run(svc.positions())
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("10")
    assert positions[0].average_price == Decimal("100")

    # SELL at a higher simulated price -> realized +100 cash.
    svc.set_reference_price(inst, make_reference(inst, last="110"))
    sell = _run(svc.submit(instrument_id=inst, side=OrderSide.SELL, quantity=10))
    assert sell.accepted is True
    assert sell.fill_price == Decimal("110")
    assert sell.net_cash == Decimal("1100")
    assert svc.funds.available_cash == Decimal("100100")

    # CLOSE: flat position (not reported).
    assert _run(svc.positions()) == []


def test_insufficient_funds_rejects_without_fill() -> None:
    inst = uuid4()
    account = make_account(starting_capital="100")
    svc = _service(account, inst, last="100")

    outcome = _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    assert outcome.accepted is False
    assert outcome.fill_price is None
    assert "insufficient" in (outcome.reason or "")
    assert svc.funds.available_cash == Decimal("100")  # unchanged
    assert _run(svc.positions()) == []


def test_position_engine_receives_normalized_fills() -> None:
    inst = uuid4()
    strategy_run_id = uuid4()
    account = make_account(starting_capital="100000")
    svc = _service(account, inst, last="100")

    buy = _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    repo = InMemoryPositionRepository()
    engine = PositionEngine(repository=repo, global_halt_active=lambda: False)
    result = engine.apply_fill(_to_fill(buy, account.account_id, strategy_run_id))

    assert result.snapshot.quantity == 10
    assert result.snapshot.status.value == "OPEN"
    snap = engine.get_position(
        strategy_run_id=strategy_run_id, instrument_id=inst, trading_mode="PAPER"
    )
    assert snap.quantity == 10


def test_reconciliation_funds_match_and_mismatch() -> None:
    inst = uuid4()
    account = make_account(starting_capital="100000")
    svc = _service(account, inst, last="100")
    _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))

    engine = ReconciliationEngine(
        repository=InMemoryReconciliationRepository(), global_halt_active=lambda: False
    )
    scope = ReconciliationScope(
        account_id=account.account_id,
        broker="paper",
        trading_mode="PAPER",
        domains=frozenset({"FUNDS"}),
    )

    # Perfect match.
    inputs = ReconciliationInputs(
        funds_internal=funds_observation_from_internal(svc.funds),
        funds_broker=funds_observation_from_broker(
            BrokerFundsSnapshot(
                broker_account_id=account.account_id,
                available_cash=svc.funds.available_cash,
            )
        ),
    )
    result = engine.run(scope=scope, inputs=inputs)
    assert result.status is RunStatus.COMPLETED
    assert result.run.matched == 1

    # Mismatch: broker reports a different cash balance.
    inputs_mismatch = ReconciliationInputs(
        funds_internal=funds_observation_from_internal(svc.funds),
        funds_broker=funds_observation_from_broker(
            BrokerFundsSnapshot(
                broker_account_id=account.account_id,
                available_cash=svc.funds.available_cash - Decimal("1"),
            )
        ),
    )
    result2 = engine.run(scope=scope, inputs=inputs_mismatch)
    kinds = {d.kind for d in result2.discrepancies}
    assert DiscrepancyKind.CASH_MISMATCH in kinds


def test_position_reconciliation_match() -> None:
    inst = uuid4()
    strategy_run_id = uuid4()
    account = make_account(starting_capital="100000")
    svc = _service(account, inst, last="100")
    buy = _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))

    repo = InMemoryPositionRepository()
    pos_engine = PositionEngine(repository=repo, global_halt_active=lambda: False)
    pos_engine.apply_fill(_to_fill(buy, account.account_id, strategy_run_id))
    internal_snap = pos_engine.get_position(
        strategy_run_id=strategy_run_id, instrument_id=inst, trading_mode="PAPER"
    )

    broker_positions = _run(svc.positions())
    assert len(broker_positions) == 1

    engine = ReconciliationEngine(
        repository=InMemoryReconciliationRepository(), global_halt_active=lambda: False
    )
    scope = ReconciliationScope(
        account_id=account.account_id,
        broker="paper",
        trading_mode="PAPER",
        domains=frozenset({"POSITIONS"}),
    )
    inputs = ReconciliationInputs(
        positions_internal=(position_observation_from_internal(internal_snap),),
        positions_broker=tuple(
            position_observation_from_broker(p) for p in broker_positions
        ),
    )
    result = engine.run(scope=scope, inputs=inputs)
    assert result.status is RunStatus.COMPLETED
    assert result.run.matched == 1


def test_persistence_restart_recovers_funds() -> None:
    inst = uuid4()
    account = make_account(starting_capital="100000")
    repo = InMemoryPaperRepository()

    svc = _service(account, inst, last="100", repository=repo)
    _run(svc.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    assert svc.funds.available_cash == Decimal("99000")

    # Rebuild the service against the same repository -> funds restored.
    svc2 = _service(account, inst, last="100", repository=repo)
    assert svc2.funds.available_cash == Decimal("99000")
