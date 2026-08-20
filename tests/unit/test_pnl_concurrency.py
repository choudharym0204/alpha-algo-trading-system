"""Phase 13 — concurrency / restart / replay tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_pnl_engine.contracts import PnlApplyStatus
from alpha_algo_pnl_engine.engine import PnlEngine

from pnl_test_support import InMemoryPnlRepository, make_fill, make_position


def make_engine(repo):
    return PnlEngine(repository=repo, global_halt_active=lambda: False)


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_concurrent_duplicate_fill_single_event():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill = make_fill(side="SELL", quantity="40", price="120", execution_id="dup")

    def work(_):
        return engine.record_fill(fill=fill, position_before=position)

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(work, range(16)))

    applied = [r for r in results if r.status == PnlApplyStatus.APPLIED]
    duplicates = [r for r in results if r.status == PnlApplyStatus.DUPLICATE]
    assert len(applied) == 1
    assert len(duplicates) == 15
    assert len(repo.events) == 1


def test_concurrent_different_fills_consistent_totals():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, strat = uuid4(), uuid4()

    def work(i):
        fill = make_fill(
            account_id=acc, strategy_run_id=strat, instrument_id=uuid4(),
            side="SELL", quantity="10", price=str(110 + i), execution_id=f"e{i}",
        )
        position = make_position(account_id=acc, strategy_run_id=strat, quantity=100, average_price="100")
        return engine.record_fill(fill=fill, position_before=position)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, range(20)))

    assert len(repo.events) == 20
    # Deterministic total: sum over i of (110+i - 100) * 10
    expected = sum((Decimal(110 + i) - Decimal(100)) * 10 for i in range(20))
    total = sum((e.net_pnl for e in repo.events.values()), Decimal("0"))
    assert total == expected


def test_restart_replay_reconstructs_realized_total():
    repo = InMemoryPnlRepository()
    acc = uuid4()
    # "Before restart": record two fills.
    engine_a = make_engine(repo)
    engine_a.record_fill(
        fill=make_fill(account_id=acc, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", quantity="40", price="120", execution_id="a"),
        position_before=make_position(account_id=acc, quantity=100, average_price="100"),
    )
    engine_a.record_fill(
        fill=make_fill(account_id=acc, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", quantity="40", price="110", execution_id="b"),
        position_before=make_position(account_id=acc, quantity=100, average_price="100"),
    )

    # "After restart": fresh engine over the same durable repository.
    engine_b = make_engine(repo)
    events = repo.list_events(account_id=acc)
    assert len(events) == 2
    total = sum((e.net_pnl for e in events), Decimal("0"))
    assert total == Decimal("1200.0000")  # 800 + 400


def test_replay_after_restart_is_duplicate_not_double_count():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, strat = uuid4(), uuid4()
    fill = make_fill(account_id=acc, strategy_run_id=strat, instrument_id=uuid4(), side="SELL", quantity="40", price="120", execution_id="a")
    position = make_position(account_id=acc, strategy_run_id=strat, quantity=100, average_price="100")

    engine.record_fill(fill=fill, position_before=position)
    # Replay the same execution after a "restart".
    result = engine.record_fill(fill=fill, position_before=position)

    assert result.status == PnlApplyStatus.DUPLICATE
    assert len(repo.events) == 1
