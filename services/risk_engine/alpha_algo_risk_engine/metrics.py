"""Risk observability metrics (Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskMetrics:
    evaluations: int = 0
    approvals: int = 0
    rejections: int = 0
    duplicates: int = 0
    persistence_failures: int = 0
    stale_data_rejections: int = 0
    circuit_breaker_trips: int = 0
    global_halt_rejections: int = 0
    context_unavailable: int = 0
    errors: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)
    total_latency: float = 0.0

    def inc(self, name: str) -> None:
        setattr(self, name, getattr(self, name) + 1)

    def inc_rule(self, rule_id: str) -> None:
        self.by_rule[rule_id] = self.by_rule.get(rule_id, 0) + 1

    def record_latency(self, seconds: float) -> None:
        self.total_latency += seconds
