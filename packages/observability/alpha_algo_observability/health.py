"""Health model (Phase 20 §27, §28).

Separates liveness, readiness, and dependency health. Trading-safety state
(``LIVE_TRADING_ENABLED`` / ``GLOBAL_TRADING_HALT``) is exposed as **read-only**
observation — the health model can never flip safety state (Phase 20 §2, §28).

An optional telemetry exporter being unavailable must not make the whole
system unhealthy (§27): dependencies are registered with an ``optional`` flag.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

__all__ = [
    "HealthStatus",
    "DependencyStatus",
    "HealthSnapshot",
    "HealthRegistry",
    "get_health_registry",
    "reset_health_registry",
]


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class DependencyStatus:
    name: str
    status: HealthStatus
    optional: bool = False
    detail: str = ""

    def to_dict(self) -> dict:
        out: dict = {"status": self.status.value, "optional": self.optional}
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class HealthSnapshot:
    status: HealthStatus
    dependencies: dict[str, DependencyStatus] = field(default_factory=dict)
    trading_safety: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "dependencies": {k: v.to_dict() for k, v in self.dependencies.items()},
            "trading_safety": self.trading_safety,
        }


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], DependencyStatus]] = {}
        self._safety: dict = {}
        self._lock = threading.Lock()

    def register(self, name: str, check: Callable[[], DependencyStatus]) -> None:
        with self._lock:
            self._checks[name] = check

    def set_trading_safety(self, **fields) -> None:
        """Record read-only trading-safety facts (never mutates trading state)."""
        with self._lock:
            self._safety.update(fields)

    def snapshot(self) -> HealthSnapshot:
        deps: dict[str, DependencyStatus] = {}
        with self._lock:
            checks = list(self._checks.items())
            safety = dict(self._safety)
        for name, check in checks:
            try:
                deps[name] = check()
            except Exception as exc:  # a failing check degrades, never crashes
                deps[name] = DependencyStatus(name=name, status=HealthStatus.UNAVAILABLE, detail=str(exc))
        status = self._aggregate(deps)
        return HealthSnapshot(status=status, dependencies=deps, trading_safety=safety)

    @staticmethod
    def _aggregate(deps: dict[str, DependencyStatus]) -> HealthStatus:
        if not deps:
            return HealthStatus.UNKNOWN
        statuses = [d.status for d in deps.values()]
        if any(s == HealthStatus.UNAVAILABLE for s, d in zip(statuses, deps.values()) if not d.optional):
            return HealthStatus.UNAVAILABLE
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        if all(s == HealthStatus.UNKNOWN for s in statuses):
            return HealthStatus.UNKNOWN
        return HealthStatus.OK


_registry: HealthRegistry | None = None
_registry_lock = threading.Lock()


def get_health_registry() -> HealthRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = HealthRegistry()
    return _registry


def reset_health_registry() -> None:
    global _registry
    with _registry_lock:
        _registry = None
