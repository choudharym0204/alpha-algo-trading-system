"""Phase 9 — deterministic execution identity tests."""

from uuid import uuid4

from alpha_algo_execution_engine.identity import (
    compute_attempt_id,
    compute_event_identity,
    compute_execution_id,
    event_content_hash,
)

from execution_test_support import make_event, make_request
from alpha_algo_execution_engine.events import OrderEventType


def test_execution_id_is_deterministic():
    oid = uuid4()
    assert compute_execution_id(oid, "k") == compute_execution_id(oid, "k")
    assert len(compute_execution_id(oid, "k")) == 64


def test_execution_id_differs_by_order():
    assert compute_execution_id(uuid4(), "k") != compute_execution_id(uuid4(), "k")


def test_execution_id_differs_by_identity_key():
    oid = uuid4()
    assert compute_execution_id(oid, "a") != compute_execution_id(oid, "b")


def test_attempt_id_is_deterministic_and_scoped():
    assert compute_attempt_id("exec-1", 0) == "exec-1-a0"
    assert compute_attempt_id("exec-1", 1) == "exec-1-a1"
    assert compute_attempt_id("exec-1", 0) != compute_attempt_id("exec-1", 1)


def test_same_request_produces_same_execution_id():
    r1 = make_request()
    r2 = make_request(order_id=r1.order_id, order_identity_key="k" * 64)
    assert r1.execution_id == r2.execution_id


def test_event_identity_prefers_source_event_id():
    oid = uuid4()
    e1 = make_event(oid, OrderEventType.FILL, fill_quantity=10, source_event_id="evt-1")
    e2 = make_event(oid, OrderEventType.FILL, fill_quantity=10, source_event_id="evt-1")
    assert compute_event_identity(e1) == compute_event_identity(e2)


def test_event_identity_differs_without_source():
    oid = uuid4()
    e1 = make_event(oid, OrderEventType.FILL, fill_quantity=10)
    e2 = make_event(oid, OrderEventType.FILL, fill_quantity=20)
    assert compute_event_identity(e1) != compute_event_identity(e2)


def test_event_content_hash_detects_payload_drift():
    oid = uuid4()
    e1 = make_event(oid, OrderEventType.FILL, fill_quantity=10, reason="a")
    e2 = make_event(oid, OrderEventType.FILL, fill_quantity=10, reason="b")
    assert event_content_hash(e1) != event_content_hash(e2)
