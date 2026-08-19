"""Phase 7 LIVE-safety / no-broker regression tests.

Phase 7 ends at the OMS handoff boundary. It must never introduce a broker
dependency, order submission, or a LIVE path.
"""

from pathlib import Path

from alpha_algo_trading_engine.state import OrchestrationState

from trading_test_support import buy_intent, make_orchestrator, make_signal_record

_TRADING_ENGINE_DIR = Path(__file__).resolve().parents[2] / "services" / "trading_engine"

# Tokens that would indicate a broker/execution/live breach inside the
# coordination layer. "handoff"/"order_type" are the legitimate OMS-ready
# boundary, not broker access.
_FORBIDDEN = (
    "requests.post",
    "http.client",
    "httpx",
    "socket",
    "urllib",
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
    "submit_order",
    "place_order",
    "execute_order",
    "broker.submit",
    "api_key",
    "secret_key",
)


def test_live_mode_is_blocked():
    orchestrator = make_orchestrator()
    result = orchestrator.process_signal(
        make_signal_record(), trading_mode="LIVE", intent=buy_intent("10")
    )
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "LIVE_MODE_BLOCKED"


def test_no_broker_or_execution_imports_in_trading_engine():
    violations = []
    for py in _TRADING_ENGINE_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            if token in text:
                violations.append((py.name, token))
    assert violations == [], f"broker/execution access detected: {violations}"


def test_oms_port_is_not_a_broker():
    from alpha_algo_trading_engine.oms_port import NoOpOmsPort

    port = NoOpOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    result = orchestrator.process_signal(
        make_signal_record(), trading_mode="PAPER", intent=buy_intent("10")
    )
    # NoOp port delivers without any external action; the flow ends here.
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.handoff_delivered is True
