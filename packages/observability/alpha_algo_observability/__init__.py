"""Public API for the Alpha Algo observability abstraction.

Provider-neutral instrumentation for metrics, structured logging, tracing,
audit, health, and alerting. No external telemetry backend is required; a
no-op / offline path is available for unit tests (§40–§42). The observability
layer is strictly a visibility/diagnostic layer — it never modifies trading
state and never enables LIVE (§2, §69).
"""

from __future__ import annotations

from .alerts import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertState,
    NoopAlertManager,
    alert_identity,
    get_alert_manager,
    reset_alert_manager,
)
from .audit import (
    AuditEvent,
    AuditRecorder,
    InMemoryAuditRecorder,
    NoopAuditRecorder,
    get_audit_recorder,
    reset_audit_recorder,
)
from .errors import FailureClass, classify_error, classify_status_code
from .health import (
    DependencyStatus,
    HealthRegistry,
    HealthSnapshot,
    HealthStatus,
    get_health_registry,
    reset_health_registry,
)
from .metrics import (
    DEFAULT_BUCKETS,
    CardinalityError,
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    NoopRegistry,
    get_metrics,
    reset_metrics,
)
from .structured_log import (
    StructuredLogger,
    get_structured_logger,
    redact,
    reset_structured_loggers,
)
from .tracing import (
    Span,
    SpanContext,
    SpanSampler,
    TraceStore,
    current_span,
    format_traceparent,
    get_trace_context,
    begin_trace,
    parse_traceparent,
    reset_trace_context,
    start_span,
)

__all__ = [
    # metrics
    "DEFAULT_BUCKETS",
    "CardinalityError",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "NoopRegistry",
    "get_metrics",
    "reset_metrics",
    # structured logging
    "StructuredLogger",
    "get_structured_logger",
    "redact",
    "reset_structured_loggers",
    # tracing
    "Span",
    "SpanContext",
    "SpanSampler",
    "TraceStore",
    "current_span",
    "format_traceparent",
    "get_trace_context",
    "begin_trace",
    "parse_traceparent",
    "reset_trace_context",
    "start_span",
    # errors
    "FailureClass",
    "classify_error",
    "classify_status_code",
    # health
    "DependencyStatus",
    "HealthRegistry",
    "HealthSnapshot",
    "HealthStatus",
    "get_health_registry",
    "reset_health_registry",
    # alerts
    "Alert",
    "AlertManager",
    "AlertSeverity",
    "AlertState",
    "NoopAlertManager",
    "alert_identity",
    "get_alert_manager",
    "reset_alert_manager",
    # audit
    "AuditEvent",
    "AuditRecorder",
    "InMemoryAuditRecorder",
    "NoopAuditRecorder",
    "get_audit_recorder",
    "reset_audit_recorder",
]

__version__ = "0.1.0"
