"""Observability failure-isolation tests (Phase 20 §42, §59, §64).

The invariant: an observability failure must degrade safely and must never
break trading. Trading failures, by contrast, must remain observable.
"""

from __future__ import annotations

from alpha_algo_observability import (
    AlertSeverity,
    FailureClass,
    HealthStatus,
    NoopAlertManager,
    NoopAuditRecorder,
    NoopRegistry,
    classify_error,
    redact,
)
from alpha_algo_observability.alerts import AlertManager
from alpha_algo_observability.health import DependencyStatus, HealthRegistry


def test_noop_metrics_never_raise_and_record_nothing() -> None:
    reg = NoopRegistry()
    c = reg.counter("orders_total", labels=("status",))
    c.inc(labels={"status": "created"})
    h = reg.histogram("latency")
    h.observe(0.5)
    g = reg.gauge("active")
    g.set(3)
    # A no-op registry exports nothing (the telemetry backend is "unavailable").
    assert reg.snapshot() == {}


def test_noop_alert_manager_never_raises() -> None:
    mgr = NoopAlertManager()
    alert = mgr.trigger(
        alert_type="broker_disconnect", severity=AlertSeverity.HIGH, source="broker",
        scope="zerodha", condition="disconnected", title="t", message="m",
    )
    assert alert.id  # returns a detached alert without recording
    assert mgr.list() == []


def test_noop_audit_never_raises() -> None:
    rec = NoopAuditRecorder()
    rec.record("login", actor="u", source="api")
    assert rec.events() == []


def test_health_check_exception_is_isolated() -> None:
    """A failing dependency check degrades the snapshot but never raises."""
    def broken():
        raise RuntimeError("dependency exploded")

    reg = HealthRegistry()
    reg.register("db", broken)
    reg.register("api", lambda: DependencyStatus(name="api", status=HealthStatus.OK))
    snap = reg.snapshot()
    assert snap.dependencies["db"].status == HealthStatus.UNAVAILABLE
    assert "dependency exploded" in snap.dependencies["db"].detail


def test_redaction_is_total_failure_safe() -> None:
    """Redaction never raises, even on unusual nested/unicode inputs."""
    assert redact({"password": b"bytes"}, key=None) == {"password": "[REDACTED]"}
    assert redact([1, {"api_key": "x"}, None]) == [1, {"api_key": "[REDACTED]"}, None]
    assert redact("\U0001F600") == "\U0001F600"


def test_trading_failure_is_observable() -> None:
    """A trading failure is normalized + can raise a deduplicated critical alert."""
    class BrokerDown(Exception):
        pass

    assert classify_error(BrokerDown()) == FailureClass.BROKER_ERROR

    mgr = AlertManager()
    a1 = mgr.trigger(
        alert_type="critical_discrepancy", severity=AlertSeverity.CRITICAL,
        source="reconciliation", scope="global", condition="position_mismatch",
        title="Critical reconciliation discrepancy", message="position mismatch detected",
    )
    a2 = mgr.trigger(
        alert_type="critical_discrepancy", severity=AlertSeverity.CRITICAL,
        source="reconciliation", scope="global", condition="position_mismatch",
        title="Critical reconciliation discrepancy", message="position mismatch detected",
    )
    # Same condition deduplicates to a single durable alert (never unlimited dupes).
    assert a1.id == a2.id
    assert len(mgr.list()) == 1
    assert mgr.list()[0]["state"] == "detected"
