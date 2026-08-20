"""Phase 8 OMS — end-to-end flow test (stops at the execution boundary)."""

from uuid import uuid4

from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_oms.boundary import ExecutionBoundary
from alpha_algo_oms.repository import OrderRepository
from alpha_algo_oms.service import OmsService

from oms_test_support import InMemoryOmsStore, OmsSessionFactory
from trading_test_support import (
    FixedIntentResolver,
    RecordingOmsPort,
    buy_intent,
    make_orchestrator,
    make_signal_record,
)


class RecordingExecutionPort:
    def __init__(self):
        self.handoffs = []

    def submit(self, handoff):
        self.handoffs.append(handoff)


def test_e2e_signal_to_submission_requested_and_stops():
    # Phase 7: StrategySignal -> Signal Engine -> RiskDecision -> Orchestrator
    #          -> TradingIntent (approved, PAPER).
    orchestrator_port = RecordingOmsPort()
    orchestrator = make_orchestrator(
        oms_port=orchestrator_port,
        intent_resolver=FixedIntentResolver(buy_intent("10", account_id=uuid4())),
    )
    record = make_signal_record()
    orchestration = orchestrator.process_signal(
        record, trading_mode="PAPER", intent=buy_intent("10", account_id=uuid4())
    )
    assert orchestration.intent is not None

    # Phase 8: OMS consumes the intent -> Internal Order -> SUBMISSION_REQUESTED
    #          -> Execution Boundary (no broker).
    store = InMemoryOmsStore()
    boundary_port = RecordingExecutionPort()
    svc = OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        execution_boundary=ExecutionBoundary(port=boundary_port),
        global_halt_active=lambda: False,
    )

    result = svc.create_order(orchestration.intent)

    assert result.status == OrderState.SUBMISSION_REQUESTED
    assert len(boundary_port.handoffs) == 1
    # The flow must STOP here — no fabricated broker ack or fill.
    assert result.status not in {
        OrderState.BROKER_ACKNOWLEDGED,
        OrderState.FILLED,
        OrderState.PARTIALLY_FILLED,
    }
    # Events persist the full internal path, nothing beyond submission.
    statuses = [e.new_status for e in store.events]
    assert statuses[-1] == OrderState.SUBMISSION_REQUESTED.value


def test_e2e_live_mode_is_rejected_before_oms():
    orchestrator_port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=orchestrator_port)
    record = make_signal_record()
    result = orchestrator.process_signal(
        record, trading_mode="LIVE", intent=buy_intent("10", account_id=uuid4())
    )
    # Phase 7 already blocks LIVE; no intent reaches the OMS.
    assert result.intent is None
    assert orchestrator_port.intents == []
