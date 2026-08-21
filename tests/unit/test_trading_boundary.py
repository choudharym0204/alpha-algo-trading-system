"""Phase 7 composition-root + signal-engine boundary wiring tests."""

from alpha_algo_risk_engine.service import RiskService
from alpha_algo_trading_engine.boundary import (
    build_trading_orchestrator,
    connect_signal_engine,
)
from alpha_algo_trading_engine.repository import TradingIntentRepository
from alpha_algo_trading_engine.state import OrchestrationState

from risk_test_support import FakeRiskProvider, FakeSessionFactory
from trading_test_support import (
    FixedIntentResolver,
    buy_intent,
    make_orchestrator,
)


def test_build_trading_orchestrator_without_repository():
    o = build_trading_orchestrator(
        risk_service=RiskService(provider=FakeRiskProvider()),
        intent_resolver=FixedIntentResolver(buy_intent("10")),
    )
    assert o._repository is None


def test_build_trading_orchestrator_with_repository():
    o = build_trading_orchestrator(
        risk_service=RiskService(provider=FakeRiskProvider()),
        session_factory=FakeSessionFactory(),
    )
    assert isinstance(o._repository, TradingIntentRepository)


def test_connect_signal_engine_wires_consumer():
    # A minimal signal-engine double exposing add_consumer.
    class FakeSignalEngine:
        def __init__(self):
            self.consumers = []

        def add_consumer(self, consumer):
            self.consumers.append(consumer)

    se = FakeSignalEngine()
    orchestrator = make_orchestrator()
    connect_signal_engine(se, orchestrator, trading_mode="PAPER")
    assert len(se.consumers) == 1

    # exercising the wired consumer runs a full orchestration
    from trading_test_support import make_signal_record

    record = make_signal_record()
    result = se.consumers[0](record)
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
