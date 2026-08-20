"""Phase 14 — concurrency tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import (
    ReconciliationInputs,
    ReconciliationScope,
)
from alpha_algo_reconciliation_engine.engine import ReconciliationEngine

from reconciliation_test_support import (
    InMemoryReconciliationRepository,
    make_position_obs,
)


def make_engine(repo):
    return ReconciliationEngine(repository=repo, global_halt_active=lambda: False)


def _scope(account_id):
    return ReconciliationScope(account_id=account_id, broker="PAPER", trading_mode="PAPER", domains=frozenset({"POSITIONS"}))


def test_concurrent_same_account_runs_dedupe_discrepancies():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc, inst = uuid4(), uuid4()
    inputs = ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc, instrument_id=inst, quantity=100),),
        positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=80),),
    )

    def work(_):
        return engine.run(scope=_scope(acc), inputs=inputs)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, range(16)))

    # Exactly one durable discrepancy survives (unique key).
    assert len(repo.discrepancies) == 1
    assert len(repo.runs) == 16  # each run is a distinct audit row


def test_concurrent_multiple_accounts_isolated():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    accounts = [uuid4() for _ in range(8)]

    def work(acc):
        inputs = ReconciliationInputs(
            positions_internal=(make_position_obs(account_id=acc, instrument_id=uuid4(), quantity=100),),
            positions_broker=(),
        )
        return engine.run(scope=_scope(acc), inputs=inputs)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, accounts))

    assert len(repo.discrepancies) == 8
    for acc in accounts:
        assert len(repo.list_discrepancies(account_id=acc)) == 1


def test_concurrent_discrepancy_writes_do_not_lose_updates():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc = uuid4()
    # Distinct instruments -> distinct discrepancy keys, no lost updates.
    insts = [uuid4() for _ in range(20)]

    def work(inst):
        inputs = ReconciliationInputs(
            positions_internal=(make_position_obs(account_id=acc, instrument_id=inst, quantity=100),),
            positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=70),),
        )
        return engine.run(scope=_scope(acc), inputs=inputs)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, insts))

    assert len(repo.list_discrepancies(account_id=acc)) == 20
