"""Phase 6 — Signal Engine → Risk Engine boundary wiring."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from alpha_algo_risk_engine.boundary import build_risk_service, connect_signal_engine
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.service import RiskService

from risk_test_support import FakeRiskProvider, FakeSessionFactory, make_buy_signal


class FakeSignalEngine:
    def __init__(self) -> None:
        self.consumers = []

    def add_consumer(self, consumer) -> None:
        self.consumers.append(consumer)


def test_build_risk_service_without_repository():
    svc = build_risk_service(provider=FakeRiskProvider())
    assert isinstance(svc, RiskService)
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "APPROVED"
    assert outcome.persisted is False  # no repository wired


def test_build_risk_service_with_repository_persists():
    factory = FakeSessionFactory(find_results=[None])
    svc = build_risk_service(provider=FakeRiskProvider(), session_factory=factory)
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.persisted is True


def test_connect_signal_engine_wires_consumer():
    risk = RiskService(provider=FakeRiskProvider())
    signal_engine = FakeSignalEngine()
    result = connect_signal_engine(signal_engine, risk)
    assert result is risk
    assert len(signal_engine.consumers) == 1


def test_connected_consumer_evaluates_persisted_signal():
    risk = RiskService(provider=FakeRiskProvider())
    signal_engine = FakeSignalEngine()
    connect_signal_engine(signal_engine, risk)

    signal = make_buy_signal()
    record = SimpleNamespace(
        signal=signal, record_id=uuid4(), identity_key="ignored", state="PERSISTED"
    )
    signal_engine.consumers[0](record)
    assert risk.metrics.evaluations == 1

    # Replaying the same signal must dedup at the risk boundary.
    signal_engine.consumers[0](record)
    assert risk.metrics.evaluations == 2
    assert risk.metrics.duplicates == 1
