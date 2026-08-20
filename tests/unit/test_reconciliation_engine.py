"""Phase 14 — reconciliation engine (run model, status, corrective workflow) tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from alpha_algo_reconciliation_engine.contracts import (
    DiscrepancyKind,
    EntityType,
    ReconciliationInputs,
    ReconciliationScope,
    RunStatus,
)
from alpha_algo_reconciliation_engine.engine import ReconciliationEngine
from alpha_algo_reconciliation_engine.errors import (
    ReconciliationModeError,
    ReconciliationPersistenceError,
    ReconciliationValidationError,
)

from reconciliation_test_support import (
    InMemoryReconciliationRepository,
    make_exec_obs,
    make_funds_obs,
    make_order_obs,
    make_position_obs,
)


def make_engine(repo=None, halt=False):
    return ReconciliationEngine(repository=repo or InMemoryReconciliationRepository(), global_halt_active=lambda: halt)


def _scope(account_id=None, broker="PAPER", mode="PAPER", domains=None):
    return ReconciliationScope(account_id=account_id or uuid4(), broker=broker, trading_mode=mode, domains=frozenset(domains) if domains else frozenset({"ORDERS", "EXECUTIONS", "POSITIONS", "FUNDS"}))


def test_full_clean_run_is_completed():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc, inst = uuid4(), uuid4()
    scope = _scope(acc)
    inputs = ReconciliationInputs(
        orders_internal=(make_order_obs(broker_order_id="B1", client_order_id="C1", account_id=acc, instrument_id=inst),),
        orders_broker=(make_order_obs(source="broker", broker_order_id="B1", client_order_id="C1", account_id=acc, instrument_id=inst),),
        executions_internal=(make_exec_obs(broker_execution_id="X1", quantity="100", price="100"),),
        executions_broker=(make_exec_obs(source="broker", broker_execution_id="X1", quantity="100", price="100"),),
        positions_internal=(make_position_obs(account_id=acc, instrument_id=inst),),
        positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst),),
        funds_internal=make_funds_obs(account_id=acc),
        funds_broker=make_funds_obs(source="broker", account_id=acc),
    )
    result = engine.run(scope=scope, inputs=inputs)
    assert result.status == RunStatus.COMPLETED
    assert result.run.matched == 4  # order + execution + position + funds
    assert result.discrepancies == ()


def test_broker_only_execution_produces_recovery_action():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc = uuid4()
    scope = _scope(acc, domains={"EXECUTIONS"})
    inputs = ReconciliationInputs(
        executions_broker=(make_exec_obs(source="broker", broker_execution_id="X9", quantity="100", price="105", side="BUY", order_id=uuid4()),),
    )
    result = engine.run(scope=scope, inputs=inputs)

    assert result.status == RunStatus.COMPLETED
    d = [x for x in result.discrepancies if x.kind == DiscrepancyKind.BROKER_ONLY][0]
    assert d.severity.value == "CRITICAL"

    actions = [a for a in result.recovery_actions if a.action_type == "ROUTE_BROKER_FILL"]
    assert len(actions) == 1
    assert actions[0].target_boundary == "execution_engine"
    assert actions[0].normalized_fill["quantity"] == "100"


def test_funds_unavailable_makes_run_partial():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc = uuid4()
    scope = _scope(acc, domains={"FUNDS"})
    inputs = ReconciliationInputs(funds_internal=make_funds_obs(account_id=acc), funds_broker=None)
    result = engine.run(scope=scope, inputs=inputs)
    assert result.status == RunStatus.PARTIAL
    assert result.run.unavailable == 1


def test_live_mode_rejected():
    engine = make_engine()
    scope = _scope(mode="LIVE")
    with pytest.raises(ReconciliationModeError):
        engine.run(scope=scope, inputs=ReconciliationInputs())


def test_halt_blocks_reconciliation():
    engine = make_engine(halt=True)
    with pytest.raises(ReconciliationValidationError):
        engine.run(scope=_scope(), inputs=ReconciliationInputs())


def test_run_persisted_and_readable():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc = uuid4()
    scope = _scope(acc, domains={"FUNDS"})
    inputs = ReconciliationInputs(funds_internal=make_funds_obs(account_id=acc), funds_broker=make_funds_obs(source="broker", account_id=acc))
    result = engine.run(scope=scope, inputs=inputs)
    loaded = engine.load_run(result.run.run_id)
    assert loaded is not None
    assert loaded.status == RunStatus.COMPLETED


def test_database_failure_does_not_report_success():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc = uuid4()
    repo.fail_next_run = True
    with pytest.raises(ReconciliationPersistenceError):
        engine.run(scope=_scope(acc, domains={"FUNDS"}), inputs=ReconciliationInputs(funds_internal=make_funds_obs(account_id=acc), funds_broker=make_funds_obs(source="broker", account_id=acc)))
    assert len(repo.runs) == 0


def test_account_isolation_between_runs():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc_a, acc_b = uuid4(), uuid4()

    engine.run(scope=_scope(acc_a, domains={"POSITIONS"}), inputs=ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc_a, instrument_id=uuid4()),),
        positions_broker=(),
    ))
    engine.run(scope=_scope(acc_b, domains={"POSITIONS"}), inputs=ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc_b, instrument_id=uuid4()),),
        positions_broker=(),
    ))

    only_a = repo.list_discrepancies(account_id=acc_a)
    assert all(d.account_id == acc_a for d in only_a)
    assert len(only_a) == 1
