"""Distributed tracing abstraction (Phase 20 §10, §11, §44).

Provides an in-process span model and a contextvar-backed current-span context
so spans propagate across ``await`` boundaries in the same async task. A W3C
``traceparent`` parser/formatter supports incoming/outgoing propagation. No
external backend is required; spans are recorded in an in-memory store and can
be sampled.

* Errors / safety events are always retained (never sampled away).
* Normal traffic is sampled with a configurable ratio.
* No invented parent/child relationships: child spans are only linked when
  started inside an active span (or explicitly with ``parent``).
"""

from __future__ import annotations

import contextvars
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Span",
    "SpanContext",
    "TraceContext",
    "TraceStore",
    "start_span",
    "begin_trace",
    "current_span",
    "parse_traceparent",
    "format_traceparent",
    "SpanSampler",
    "get_trace_context",
    "reset_trace_context",
]

TRACE_FLAG_SAMPLED = 0x01


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    sampled: bool = True


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    start: float = field(default_factory=time.perf_counter)
    end: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "unset"
    error: bool = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str, error: bool = False) -> None:
        self.status = status
        self.error = error

    def finish(self) -> None:
        if self.end is None:
            self.end = time.perf_counter()

    @property
    def duration_ms(self) -> float | None:
        if self.end is None:
            return None
        return round((self.end - self.start) * 1000, 3)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "status": self.status,
            "error": self.error,
        }


class SpanSampler:
    """Retain errors/safety always; sample normal traffic at ``ratio``."""

    def __init__(self, ratio: float = 1.0, *, rng: random.Random | None = None) -> None:
        if not 0.0 <= ratio <= 1.0:
            raise ValueError("sampling ratio must be in [0, 1]")
        self.ratio = ratio
        self._rng = rng or random.Random()

    def should_sample(self, *, error: bool = False, safety: bool = False) -> bool:
        if error or safety:
            return True
        return self._rng.random() < self.ratio


class TraceContext:
    """A single trace context (trace id + current span stack)."""

    def __init__(self, trace_id: str, *, sampled: bool = True) -> None:
        self.trace_id = trace_id
        self.sampled = sampled

    @property
    def context(self) -> SpanContext:
        parent = self._current_span_var.get()
        span_id = parent.span_id if parent else _new_id()
        return SpanContext(trace_id=self.trace_id, span_id=span_id, sampled=self.sampled)


_current_span_var: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "alpha_algo_current_span", default=None
)
_current_context_var: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "alpha_algo_trace_context", default=None
)


class TraceStore:
    def __init__(self) -> None:
        self._spans: list[Span] = []
        self._lock = threading.Lock()

    def add(self, span: Span) -> None:
        with self._lock:
            self._spans.append(span)

    def spans(self, trace_id: str | None = None) -> list[dict]:
        with self._lock:
            items = self._spans if trace_id is None else [s for s in self._spans if s.trace_id == trace_id]
            return [s.to_dict() for s in items]

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


class _SpanScope:
    def __init__(self, span: Span, store: TraceStore, token: contextvars.Token) -> None:
        self._span = span
        self._store = store
        self._token = token

    def __enter__(self) -> Span:
        return self._span

    def __exit__(self, *exc_info) -> None:
        self._span.finish()
        if exc_info[0] is not None:
            self._span.set_status("error", error=True)
        self._store.add(self._span)
        _current_span_var.reset(self._token)


def _new_context(trace_id: str, *, sampled: bool) -> TraceContext:
    ctx = TraceContext(trace_id, sampled=sampled)
    _current_context_var.set(ctx)
    return ctx


def begin_trace(trace_id: str | None = None, *, sampled: bool = True) -> TraceContext:
    """Start (or adopt) a trace context in the current async task.

    ``trace_id`` is usually taken from an inbound ``traceparent`` header so the
    local span links to the upstream trace."""
    tid = trace_id or _new_id()
    return _new_context(tid, sampled=sampled)


def current_span() -> Span | None:
    return _current_span_var.get()


def start_span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    store: TraceStore | None = None,
    parent: Span | None = None,
) -> _SpanScope:
    """Start a span, returning a context manager. Child linkage is derived from
    the currently-active span unless ``parent`` is passed explicitly."""
    parent = parent or _current_span_var.get()
    trace_id = parent.trace_id if parent else (_current_context_var.get().trace_id if _current_context_var.get() else _new_id())
    span = Span(
        name=name,
        trace_id=trace_id,
        span_id=_new_id(),
        parent_span_id=parent.span_id if parent else None,
        attributes=attributes or {},
    )
    store = store or get_trace_context().store
    token = _current_span_var.set(span)
    return _SpanScope(span, store, token)


class _DefaultTraceContext:
    def __init__(self) -> None:
        self.store = TraceStore()
        self.sampler = SpanSampler(ratio=1.0)


_default: _DefaultTraceContext | None = None
_default_lock = threading.Lock()


def get_trace_context() -> _DefaultTraceContext:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = _DefaultTraceContext()
    return _default


def reset_trace_context() -> None:
    global _default
    with _default_lock:
        _default = None


def parse_traceparent(header: str) -> SpanContext | None:
    """Parse a W3C ``traceparent`` header: ``00-<traceid>-<spanid>-<flags>``."""
    try:
        version, trace_id, span_id, flags = header.strip().split("-")
    except (ValueError, AttributeError):
        return None
    if version != "00":
        return None
    if len(trace_id) != 32 or len(span_id) != 16:
        return None
    try:
        int(trace_id, 16)
        int(span_id, 16)
        flag_int = int(flags, 16)
    except ValueError:
        return None
    return SpanContext(trace_id=trace_id, span_id=span_id, sampled=bool(flag_int & TRACE_FLAG_SAMPLED))


def format_traceparent(context: SpanContext) -> str:
    flags = "01" if context.sampled else "00"
    return f"00-{context.trace_id}-{context.span_id}-{flags}"
