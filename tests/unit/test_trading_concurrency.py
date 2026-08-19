"""Phase 7 concurrency-safety tests (no global locks, narrow idempotency guard)."""

import threading

from alpha_algo_trading_engine.state import OrchestrationState

from trading_test_support import (
    RecordingOmsPort,
    buy_intent,
    make_orchestrator,
    make_signal_record,
)


def test_concurrent_same_signal_yields_single_intent():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    record = make_signal_record()
    intent = buy_intent("10")
    n = 8
    results = [None] * n

    def worker(i):
        results[i] = orchestrator.process_signal(record, trading_mode="PAPER", intent=intent)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    states = [r.state for r in results]
    assert states.count(OrchestrationState.OMS_HANDOFF_READY) == 1
    assert states.count(OrchestrationState.DUPLICATE) == n - 1
    assert len(port.intents) == 1


def test_concurrent_distinct_signals_all_handoff():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    n = 8
    records = [make_signal_record() for _ in range(n)]
    results = [None] * n

    def worker(i):
        results[i] = orchestrator.process_signal(
            records[i], trading_mode="PAPER", intent=buy_intent("10")
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r.state == OrchestrationState.OMS_HANDOFF_READY for r in results)
    assert len(port.intents) == n
    # no duplicate orchestration identities across distinct signals
    ids = {i.orchestration_id for i in port.intents}
    assert len(ids) == n


def test_multiple_accounts_do_not_collide():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    from uuid import uuid4

    record = make_signal_record()
    a = orchestrator.process_signal(
        record, trading_mode="PAPER", intent=buy_intent("10", account_id=uuid4())
    )
    b = orchestrator.process_signal(
        record, trading_mode="PAPER", intent=buy_intent("10", account_id=uuid4())
    )
    assert a.state == OrchestrationState.OMS_HANDOFF_READY
    assert b.state == OrchestrationState.OMS_HANDOFF_READY
    assert len(port.intents) == 2
