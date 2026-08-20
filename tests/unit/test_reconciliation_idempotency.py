"""Phase 14 — idempotency / replay / conflict tests."""

from __future__ import annotations

from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import (
    DiscrepancyKind,
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


def test_replay_does_not_duplicate_discrepancy():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc, inst = uuid4(), uuid4()
    inputs = ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc, instrument_id=inst, quantity=100),),
        positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=80),),
    )

    r1 = engine.run(scope=_scope(acc), inputs=inputs)
    r2 = engine.run(scope=_scope(acc), inputs=inputs)

    assert len(r1.discrepancies) == 1
    assert r2.discrepancies == ()  # idempotent: no new discrepancies
    assert len(repo.discrepancies) == 1  # not duplicated


def test_same_identity_different_evidence_is_conflict():
    repo = InMemoryReconciliationRepository()
    engine = make_engine(repo)
    acc, inst = uuid4(), uuid4()

    inputs_a = ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc, instrument_id=inst, quantity=100),),
        positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=80),),
    )
    inputs_b = ReconciliationInputs(
        positions_internal=(make_position_obs(account_id=acc, instrument_id=inst, quantity=100),),
        positions_broker=(make_position_obs(source="broker", account_id=acc, instrument_id=inst, quantity=90),),
    )

    r1 = engine.run(scope=_scope(acc), inputs=inputs_a)
    r2 = engine.run(scope=_scope(acc), inputs=inputs_b)

    assert r2.run.conflicts == 1
    kinds = {d.kind for d in repo.discrepancies.values()}
    assert DiscrepancyKind.QUANTITY_MISMATCH in kinds
    assert DiscrepancyKind.CONFLICT in kinds

    # Original evidence preserved (broker quantity still 80, not overwritten to 90).
    original = [d for d in repo.discrepancies.values() if d.kind == DiscrepancyKind.QUANTITY_MISMATCH][0]
    assert original.broker_state["quantity"] == 80
