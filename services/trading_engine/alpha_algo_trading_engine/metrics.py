"""Trading-orchestrator observability metrics (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrchestrationMetrics:
    signals_received: int = 0
    signals_rejected: int = 0
    risk_calls: int = 0
    risk_approvals: int = 0
    risk_rejections: int = 0
    duplicates: int = 0
    duplicate_intents: int = 0
    persistence_failures: int = 0
    oms_handoff_failures: int = 0
    errors: int = 0
    by_state: dict[str, int] = field(default_factory=dict)
    total_latency: float = 0.0

    def inc(self, name: str) -> None:
        setattr(self, name, getattr(self, name) + 1)

    def record_state(self, state: str) -> None:
        self.by_state[state] = self.by_state.get(state, 0) + 1

    def record_latency(self, seconds: float) -> None:
        self.total_latency += seconds
