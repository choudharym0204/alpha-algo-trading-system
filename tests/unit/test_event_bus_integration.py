"""Integration test: the internal trading pipeline as a correlated event flow.

Demonstrates that the unified envelope + bus can carry the full pipeline
(signal → risk → orchestration → OMS → execution → position → P&L →
reconciliation) as a causally-linked, reconstructable event stream for
cross-cutting subscribers — without changing the tested synchronous engines.
"""

from __future__ import annotations

from alpha_algo_contracts import DomainEvent, EventType, create_event
from alpha_algo_event_bus import EventBus


def _pipeline_events() -> list[DomainEvent]:
    corr = "corr-pipeline-1"
    trace = "trace-1"

    signal = create_event(
        event_type=EventType.SIGNAL_ACCEPTED,
        source="signal-engine",
        correlation_id=corr,
        trace_id=trace,
        domain_ids={"signal_id": "sig-1", "strategy_run_id": "run-1"},
    )
    risk = signal.derive(
        event_type=EventType.RISK_DECISION,
        payload={"decision": "APPROVED"},
        domain_ids={"risk_decision_id": "risk-1"},
    )
    intent = risk.derive(
        event_type=EventType.INTENT_CREATED,
        payload={"action": "BUY", "quantity": "10"},
        domain_ids={"orchestration_id": "orch-1"},
    )
    order = intent.derive(
        event_type=EventType.ORDER_CREATED,
        domain_ids={"order_id": "ord-1"},
    )
    submitted = order.derive(
        event_type=EventType.EXECUTION_SUBMITTED,
        domain_ids={"execution_id": "exec-1"},
    )
    filled = submitted.derive(
        event_type=EventType.EXECUTION_FILLED,
        payload={"fill_quantity": "10"},
        domain_ids={"execution_id": "exec-1"},
    )
    position = filled.derive(
        event_type=EventType.POSITION_UPDATED,
        payload={"quantity": "10"},
        domain_ids={"position_id": "pos-1"},
    )
    pnl = position.derive(
        event_type=EventType.PNL_REALIZED,
        payload={"amount": "1.23"},
        domain_ids={"pnl_event_id": "pnl-1"},
    )
    reconciliation = pnl.derive(
        event_type=EventType.RECONCILIATION_COMPLETED,
        payload={"matches": "5"},
        domain_ids={"reconciliation_run_id": "recon-1"},
    )
    return [signal, risk, intent, order, submitted, filled, position, pnl, reconciliation]


def test_pipeline_event_flow_is_reconstructable() -> None:
    bus = EventBus()
    audit: list[DomainEvent] = []
    bus.subscribe("*", audit.append)

    events = _pipeline_events()
    bus.publish_many(events)

    assert len(audit) == 9
    assert [e.event_type for e in audit] == [
        "signal.accepted",
        "risk.decision",
        "intent.created",
        "order.created",
        "execution.submitted",
        "execution.filled",
        "position.updated",
        "pnl.realized",
        "reconciliation.completed",
    ]

    # Correlation + trace preserved across the whole lifecycle.
    assert all(e.correlation_id == "corr-pipeline-1" for e in audit)
    assert all(e.trace_id == "trace-1" for e in audit)

    # Causation chain: each event points at its immediate parent.
    for i in range(1, len(audit)):
        assert audit[i].causation_id == str(audit[i - 1].event_id)

    # Domain ids accumulate and remain reconstructable (never replaced).
    ids = {k: v for e in audit for k, v in e.domain_ids.items()}
    assert ids["signal_id"] == "sig-1"
    assert ids["orchestration_id"] == "orch-1"
    assert ids["order_id"] == "ord-1"
    assert ids["execution_id"] == "exec-1"
    assert ids["position_id"] == "pos-1"
    assert ids["pnl_event_id"] == "pnl-1"
    assert ids["reconciliation_run_id"] == "recon-1"


def test_cross_cutting_subscribers_are_decoupled() -> None:
    bus = EventBus()
    observability: list[str] = []
    audit: list[str] = []
    notification: list[str] = []

    bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, lambda e: observability.append(e.event_type))
    bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, lambda e: audit.append(e.event_type))
    bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, lambda e: notification.append(e.event_type))

    bus.publish(
        create_event(
            event_type=EventType.RECONCILIATION_DISCREPANCY,
            source="reconciliation-engine",
            payload={"kind": "POSITION_MISMATCH", "severity": "CRITICAL"},
            domain_ids={"discrepancy_id": "disc-1"},
        )
    )

    assert observability == audit == notification == ["reconciliation.discrepancy"]


def test_handler_failure_does_not_break_cross_cutting_flow() -> None:
    bus = EventBus()
    received: list[str] = []

    def noisy(_event: DomainEvent) -> None:
        raise RuntimeError("subscriber down")

    bus.subscribe(EventType.PNL_REALIZED, noisy)
    bus.subscribe(EventType.PNL_REALIZED, lambda e: received.append(e.event_type))

    bus.publish(create_event(event_type=EventType.PNL_REALIZED, source="pnl-engine"))

    # The healthy subscriber still receives the event despite the failure.
    assert received == ["pnl.realized"]
    assert len(bus.failures()) == 1
