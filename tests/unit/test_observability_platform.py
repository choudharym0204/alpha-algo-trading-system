"""Unit tests for the provider-neutral observability abstraction.

Covers metrics (counter/gauge/histogram + cardinality), structured-log
redaction, tracing (spans + traceparent), error normalization, health
aggregation, alert dedup + lifecycle, and append-only audit chaining.
"""

from __future__ import annotations

import pytest

from alpha_algo_observability import (
    AlertSeverity,
    AlertState,
    CardinalityError,
    FailureClass,
    HealthStatus,
    InMemoryAuditRecorder,
    MetricsRegistry,
    classify_error,
    classify_status_code,
    format_traceparent,
    parse_traceparent,
    redact,
    reset_metrics,
)
from alpha_algo_observability.alerts import AlertManager, alert_identity
from alpha_algo_observability.health import DependencyStatus, HealthRegistry
from alpha_algo_observability.tracing import SpanSampler, start_span, get_trace_context, reset_trace_context


@pytest.fixture(autouse=True)
def _reset_globals():
    reset_metrics()
    reset_trace_context()
    yield
    reset_metrics()
    reset_trace_context()


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def test_counter_increments():
    reg = MetricsRegistry()
    c = reg.counter("orders_total", labels=("status",))
    c.inc(labels={"status": "created"})
    c.inc(2, labels={"status": "created"})
    c.inc(labels={"status": "rejected"})
    assert c.get(labels={"status": "created"}) == 3.0
    assert c.get(labels={"status": "rejected"}) == 1.0
    snap = reg.snapshot()
    assert snap["orders_total"]["type"] == "counter"


def test_gauge_set_and_snapshot():
    reg = MetricsRegistry()
    g = reg.gauge("active_connections")
    g.set(5)
    g.inc(2)
    g.dec(1)
    assert g.get() == 6.0


def test_histogram_buckets_and_observe():
    reg = MetricsRegistry()
    h = reg.histogram("latency", buckets=(0.01, 0.1, 1.0))
    h.observe(0.005)
    h.observe(0.05)
    h.observe(2.0)
    snap = h.snapshot()
    assert snap["count"] == 3
    assert snap["counts"] == [1, 1, 0, 1]  # <=0.01, (0.01,0.1], (0.1,1.0], >1.0
    assert snap["total"] == pytest.approx(2.055)


def test_cardinality_unknown_label_raises():
    reg = MetricsRegistry()
    c = reg.counter("m", labels=("status",))
    with pytest.raises(CardinalityError):
        c.inc(labels={"status": "ok", "user_id": "abc"})


def test_cardinality_missing_label_raises():
    reg = MetricsRegistry()
    c = reg.counter("m", labels=("status",))
    with pytest.raises(CardinalityError):
        c.inc(labels={})


def test_cardinality_long_value_raises():
    reg = MetricsRegistry()
    c = reg.counter("m", labels=("status",))
    with pytest.raises(CardinalityError):
        c.inc(labels={"status": "x" * 200})


# --------------------------------------------------------------------------- #
# Structured logging (redaction)
# --------------------------------------------------------------------------- #

def test_redact_sensitive_keys():
    assert redact("s3cret", key="password") == "[REDACTED]"
    assert redact({"Authorization": "Bearer abc", "user": "alice"}) == {
        "Authorization": "[REDACTED]",
        "user": "alice",
    }


def test_redact_nested_and_plain():
    value = {"nested": {"api_key": "k"}, "ok": 1}
    assert redact(value) == {"nested": {"api_key": "[REDACTED]"}, "ok": 1}
    assert redact("hello") == "hello"


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #

def test_traceparent_roundtrip():
    ctx = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    assert ctx is not None
    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.sampled is True
    assert format_traceparent(ctx).startswith("00-")


def test_traceparent_invalid_rejected():
    assert parse_traceparent("garbage") is None
    assert parse_traceparent("00-short-short-01") is None


def test_span_parent_child_linkage():
    ctx = get_trace_context()
    ctx.store.clear()
    with start_span("outer") as outer:
        assert outer.parent_span_id is None
        with start_span("inner") as inner:
            assert inner.parent_span_id == outer.span_id
            assert inner.trace_id == outer.trace_id
    spans = ctx.store.spans()
    assert len(spans) == 2


def test_sampler_never_drops_errors():
    sampler = SpanSampler(ratio=0.0)
    assert sampler.should_sample(error=False) is False
    assert sampler.should_sample(error=True) is True
    assert sampler.should_sample(safety=True) is True


# --------------------------------------------------------------------------- #
# Error normalization
# --------------------------------------------------------------------------- #

def test_classify_status_codes():
    assert classify_status_code(401) == FailureClass.AUTHENTICATION_FAILURE
    assert classify_status_code(403) == FailureClass.AUTHORIZATION_FAILURE
    assert classify_status_code(429) == FailureClass.RATE_LIMIT
    assert classify_status_code(422) == FailureClass.VALIDATION_FAILURE
    assert classify_status_code(500) == FailureClass.PROVIDER_UNAVAILABLE
    assert classify_status_code(503) == FailureClass.PROVIDER_UNAVAILABLE


def test_classify_by_code():
    assert classify_error(None, code="AUTH_REQUIRED") == FailureClass.AUTHENTICATION_FAILURE
    assert classify_error(None, code="FORBIDDEN") == FailureClass.AUTHORIZATION_FAILURE
    assert classify_error(None, code="RATE_LIMITED") == FailureClass.RATE_LIMIT


def test_classify_by_exception_type():
    class BrokerTimeout(Exception):
        pass

    assert classify_error(BrokerTimeout()) == FailureClass.TIMEOUT
    assert classify_error(ValueError()) == FailureClass.UNKNOWN


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

def test_health_aggregate_ok_and_optional():
    reg = HealthRegistry()
    reg.register("db", lambda: DependencyStatus(name="db", status=HealthStatus.OK))
    reg.register(
        "telemetry",
        lambda: DependencyStatus(name="telemetry", status=HealthStatus.UNAVAILABLE, optional=True),
    )
    snap = reg.snapshot()
    assert snap.status == HealthStatus.OK  # optional dep does not fail the system
    assert snap.dependencies["telemetry"].status == HealthStatus.UNAVAILABLE


def test_health_aggregate_unavailable_required():
    reg = HealthRegistry()
    reg.register("db", lambda: DependencyStatus(name="db", status=HealthStatus.UNAVAILABLE))
    snap = reg.snapshot()
    assert snap.status == HealthStatus.UNAVAILABLE


def test_health_check_exception_degrades():
    def boom():
        raise RuntimeError("down")

    reg = HealthRegistry()
    reg.register("db", boom)
    snap = reg.snapshot()
    assert snap.status == HealthStatus.UNAVAILABLE
    assert "down" in snap.dependencies["db"].detail


def test_health_trading_safety_readonly():
    reg = HealthRegistry()
    reg.set_trading_safety(LIVE_TRADING_ENABLED=False, GLOBAL_TRADING_HALT=True)
    snap = reg.snapshot()
    assert snap.trading_safety == {"LIVE_TRADING_ENABLED": False, "GLOBAL_TRADING_HALT": True}


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #

def test_alert_dedup_by_identity():
    mgr = AlertManager()
    a1 = mgr.trigger(
        alert_type="broker_disconnect", severity=AlertSeverity.HIGH, source="broker",
        scope="zerodha", condition="disconnected", title="Broker down", message="broker down",
    )
    a2 = mgr.trigger(
        alert_type="broker_disconnect", severity=AlertSeverity.HIGH, source="broker",
        scope="zerodha", condition="disconnected", title="Broker down", message="broker down",
    )
    assert a1.id == a2.id  # deduplicated
    assert len(mgr.list()) == 1


def test_alert_different_condition_not_deduped():
    mgr = AlertManager()
    mgr.trigger(alert_type="x", severity=AlertSeverity.WARNING, source="s", scope="a", condition="c1", title="t", message="m")
    mgr.trigger(alert_type="x", severity=AlertSeverity.WARNING, source="s", scope="a", condition="c2", title="t", message="m")
    assert len(mgr.list()) == 2


def test_alert_lifecycle_transitions_auditable():
    mgr = AlertManager()
    a = mgr.trigger(
        alert_type="risk", severity=AlertSeverity.CRITICAL, source="risk", scope="global",
        condition="halt", title="Halt", message="halted",
    )
    mgr.acknowledge(a.id)
    mgr.escalate(a.id)
    mgr.resolve(a.id)
    final = mgr.get(a.id)
    assert final.state == AlertState.RESOLVED
    states = [t["to"] for t in final.transitions]
    assert states == ["detected", "acknowledged", "escalated", "resolved"]


def test_alert_identity_is_deterministic():
    assert alert_identity(alert_type="a", source="s", scope="x", condition="c") == alert_identity(
        alert_type="a", source="s", scope="x", condition="c"
    )


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #

def test_audit_append_only_chaining():
    rec = InMemoryAuditRecorder()
    e1 = rec.record("login", actor="u1", source="api", status="ok", fields={"ip": "1.2.3.4"})
    e2 = rec.record("logout", actor="u1", source="api", status="ok")
    events = rec.events()
    assert len(events) == 2
    assert events[0]["previous_event_hash"] is None
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    assert events[1]["event_hash"] != events[0]["event_hash"]


def test_audit_events_immutable_list():
    rec = InMemoryAuditRecorder()
    rec.record("a", source="s")
    first = rec.events()
    first.append({"tampered": True})  # mutating the returned list must not affect the recorder
    assert len(rec.events()) == 1
