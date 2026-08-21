"""Provider-neutral metrics abstraction: Counter, Gauge, Histogram.

Design goals (Phase 20 §12, §37, §50):

* In-memory, thread-safe, no external backend required.
* Labels are **bounded**: each metric family declares its label keys up front;
  unknown keys raise, and unbounded values are rejected to prevent cardinality
  explosion. Detailed identifiers (order ids, user ids, symbols, raw
  timestamps, exception strings) must never be metric labels — they belong in
  structured logs / traces / audit / domain databases.
* A no-op registry is provided so unit tests and offline execution never
  require a telemetry backend.

A small global default registry is exposed for convenience, but callers that
need isolation (tests, multiple app instances) can construct their own
``MetricsRegistry``.
"""

from __future__ import annotations

import bisect
import threading
from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "CardinalityError",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "NoopRegistry",
    "get_metrics",
    "reset_metrics",
    "DEFAULT_BUCKETS",
]

# Shared latency buckets (seconds): 1ms .. 60s, exponentially spaced.
DEFAULT_BUCKETS = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25,
    0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
)

MAX_LABEL_VALUE_LENGTH = 128


class CardinalityError(ValueError):
    """Raised when a metric label would violate the bounded-cardinality policy."""


def _resolve_labels(
    spec: tuple[str, ...],
    labels: dict[str, str] | None,
) -> tuple[str, ...]:
    labels = labels or {}
    unknown = set(labels) - set(spec)
    if unknown:
        raise CardinalityError(f"unknown label(s) {sorted(unknown)} for labels={spec}")
    missing = [k for k in spec if k not in labels]
    if missing:
        raise CardinalityError(f"missing label(s) {sorted(missing)} for labels={spec}")
    for key in spec:
        value = labels[key]
        if not isinstance(value, str):
            raise CardinalityError(f"label {key!r} must be a string")
        if len(value) > MAX_LABEL_VALUE_LENGTH:
            raise CardinalityError(f"label {key!r} value exceeds {MAX_LABEL_VALUE_LENGTH} chars")
    return tuple(labels[k] for k in spec)


@dataclass
class _CounterSeries:
    value: float = 0.0


@dataclass
class _GaugeSeries:
    value: float = 0.0


@dataclass
class _HistogramSeries:
    buckets: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            # len(buckets) + 1 bins: <=b0, (b0,b1], ..., >b[-1]
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        value = float(value)
        self.count += 1
        self.total += value
        idx = bisect.bisect_right(self.buckets, value)
        self.counts[idx] += 1

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "total": self.total,
            "buckets": list(self.buckets),
            "counts": list(self.counts),
        }


class Counter:
    def __init__(self, name: str, description: str = "", labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.labels = labels
        self._series: dict[tuple[str, ...], _CounterSeries] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.setdefault(key, _CounterSeries())
            series.value += amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.get(key)
            return series.value if series else 0.0


class Gauge:
    def __init__(self, name: str, description: str = "", labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.labels = labels
        self._series: dict[tuple[str, ...], _GaugeSeries] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.setdefault(key, _GaugeSeries())
            series.value = float(value)

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.setdefault(key, _GaugeSeries())
            series.value += amount

    def dec(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self.inc(-amount, labels)

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.get(key)
            return series.value if series else 0.0


class Histogram:
    def __init__(
        self,
        name: str,
        description: str = "",
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
    ) -> None:
        self.name = name
        self.description = description
        self.labels = labels
        self.buckets = tuple(sorted(buckets))
        self._series: dict[tuple[str, ...], _HistogramSeries] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.get(key)
            if series is None:
                series = _HistogramSeries(buckets=self.buckets)
                self._series[key] = series
            series.observe(value)

    def snapshot(self, labels: dict[str, str] | None = None) -> dict:
        key = _resolve_labels(self.labels, labels)
        with self._lock:
            series = self._series.get(key)
            if series is None:
                return {"count": 0, "total": 0.0, "buckets": list(self.buckets), "counts": []}
            return series.snapshot()


class MetricsRegistry:
    """A named collection of metrics with a uniform snapshot/export API."""

    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Gauge | Histogram] = {}
        self._lock = threading.Lock()

    def register(self, metric: Counter | Gauge | Histogram) -> Counter | Gauge | Histogram:
        with self._lock:
            if metric.name in self._metrics:
                existing = self._metrics[metric.name]
                if type(existing) is not type(metric):
                    raise ValueError(f"metric {metric.name!r} already registered with a different type")
                return existing
            self._metrics[metric.name] = metric
            return metric

    def counter(self, name: str, description: str = "", labels: tuple[str, ...] = ()) -> Counter:
        return self.register(Counter(name, description, labels))  # type: ignore[return-value]

    def gauge(self, name: str, description: str = "", labels: tuple[str, ...] = ()) -> Gauge:
        return self.register(Gauge(name, description, labels))  # type: ignore[return-value]

    def histogram(
        self,
        name: str,
        description: str = "",
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
    ) -> Histogram:
        return self.register(Histogram(name, description, labels, buckets))  # type: ignore[return-value]

    def get(self, name: str) -> Counter | Gauge | Histogram | None:
        with self._lock:
            return self._metrics.get(name)

    def snapshot(self) -> dict:
        """Export a JSON-serializable snapshot of every metric family."""
        out: dict[str, dict] = {}
        with self._lock:
            for name, metric in self._metrics.items():
                out[name] = {
                    "type": metric.__class__.__name__.lower(),
                    "description": metric.description,
                    "labels": list(metric.labels),
                    "samples": self._samples(metric),
                }
        return out

    @staticmethod
    def _samples(metric: Counter | Gauge | Histogram) -> list[dict]:
        if isinstance(metric, (Counter, Gauge)):
            return [
                {"labels": dict(zip(metric.labels, key)), "value": series.value}
                for key, series in metric._series.items()
            ]
        return [
            {"labels": dict(zip(metric.labels, key)), **series.snapshot()}
            for key, series in metric._series.items()
        ]


class NoopRegistry(MetricsRegistry):
    """A registry whose metrics accept calls but record nothing (offline/tests)."""

    def register(self, metric: Counter | Gauge | Histogram) -> Counter | Gauge | Histogram:
        return metric


_DEFAULT_REGISTRY: MetricsRegistry | None = None
_REGISTRY_LOCK = threading.Lock()


def get_metrics() -> MetricsRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = MetricsRegistry()
    return _DEFAULT_REGISTRY


def reset_metrics() -> None:
    global _DEFAULT_REGISTRY
    with _REGISTRY_LOCK:
        _DEFAULT_REGISTRY = None
