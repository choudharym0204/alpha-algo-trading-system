"""Phase 8 OMS — LIVE-safety / security-boundary tests."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from alpha_algo_execution_engine.submission import BrokerSubmissionIntent
from alpha_algo_oms.boundary import ExecutionBoundary, NoOpExecutionPort, SubmissionHandoff
from alpha_algo_oms.errors import OrderValidationError, TradingModeError
from alpha_algo_oms.service import OmsService

from oms_test_support import expired_intent, make_intent

OMS_DIR = Path(__file__).resolve().parents[2] / "services" / "oms"


def _source_text() -> str:
    text = []
    for path in OMS_DIR.rglob("*.py"):
        text.append(path.read_text(encoding="utf-8"))
    return "\n".join(text)


def test_oms_service_has_no_force_filled_api():
    # The OMS must not expose any privileged lifecycle-transition API.
    public = [m for m in dir(OmsService) if not m.startswith("_")]
    assert "force_filled" not in public
    assert "acknowledge" not in public
    assert "mark_filled" not in public
    assert "mark_cancelled" not in public
    assert "reconcile" not in public


def test_no_broker_sdk_or_credentials_in_source():
    src = _source_text().lower()
    for forbidden in (
        "alpaca", "ib_insync", "ccxt", "broker_api_key", "broker_secret",
        "api_secret", "access_token", "requests.post",
    ):
        assert forbidden not in src, f"forbidden token {forbidden!r} in OMS source"


def test_default_boundary_is_noop_not_broker():
    boundary = ExecutionBoundary()
    assert isinstance(boundary._port, NoOpExecutionPort)


def test_submission_handoff_has_no_broker_order_id():
    # broker_order_id is a Phase-9 placeholder and must never be fabricated.
    handoff = SubmissionHandoff(
        order_id=uuid4(),
        broker_submission_intent=BrokerSubmissionIntent(
            order_id=uuid4(), signal_id=uuid4(), strategy_id=uuid4(),
            instrument_id=uuid4(), risk_approval_id=uuid4(),
            requested_at=datetime.now(UTC), metadata={},
        ),
    )
    assert not hasattr(handoff, "broker_order_id")


def test_live_mode_rejected():
    svc = OmsService(global_halt_active=lambda: False)
    with pytest.raises(TradingModeError):
        svc.create_order(make_intent(trading_mode="LIVE"))


def test_expired_approval_cannot_be_reused():
    svc = OmsService(global_halt_active=lambda: False)
    with pytest.raises(OrderValidationError):
        svc.create_order(expired_intent())


def test_oms_has_no_broker_submission_import():
    src = _source_text()
    for forbidden_import in (
        "alpha_algo_broker", "paper_broker", "broker_adapters",
    ):
        assert forbidden_import not in src, f"broker coupling: {forbidden_import}"


def test_oms_package_exports_execution_port_only():
    import alpha_algo_oms

    assert hasattr(alpha_algo_oms, "ExecutionPort")
    assert hasattr(alpha_algo_oms, "ExecutionBoundary")
    # no broker-facing symbols beyond the NoOp placeholder
    broker_names = [n for n in dir(alpha_algo_oms) if "broker" in n.lower()]
    assert broker_names == []
