from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_contracts import (
    RiskAssessmentRequest,
    RiskDecisionResult,
    SignalAction,
    StrategySignal,
)
from alpha_algo_risk_engine import RiskEvaluationContext, RiskRuleEngine, RiskTradingMode


FIXED_NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def _ids():
    values = [
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
        UUID("00000000-0000-0000-0000-000000000003"),
    ]

    def next_id() -> UUID:
        return values.pop(0)

    return next_id


def _request() -> RiskAssessmentRequest:
    return RiskAssessmentRequest(
        request_id=UUID("10000000-0000-0000-0000-000000000001"),
        signal=StrategySignal(
            signal_id=UUID("20000000-0000-0000-0000-000000000001"),
            strategy_id=UUID("30000000-0000-0000-0000-000000000001"),
            strategy_version="1.0.0",
            strategy_config_hash="sha256:config",
            instrument_id=UUID("40000000-0000-0000-0000-000000000001"),
            action=SignalAction.BUY,
            timestamp=FIXED_NOW,
            confidence=Decimal("0.80"),
            reason="indicator threshold crossed",
        ),
        requested_at=FIXED_NOW,
    )


def _passing_context() -> RiskEvaluationContext:
    return RiskEvaluationContext(
        trading_mode=RiskTradingMode.PAPER,
        live_trading_enabled=False,
        global_halt_active=False,
        broker_connected=True,
        market_data_fresh=True,
        market_session_open=True,
        instrument_allowed=True,
        duplicate_signal=False,
        order_quantity=Decimal("10"),
        max_order_quantity=Decimal("100"),
        projected_position_quantity=Decimal("25"),
        max_position_quantity=Decimal("100"),
        projected_exposure=Decimal("2500"),
        max_exposure=Decimal("10000"),
        daily_realized_pnl=Decimal("-100"),
        max_daily_loss=Decimal("1000"),
        strategy_realized_pnl=Decimal("-50"),
        max_strategy_loss=Decimal("500"),
        required_margin=Decimal("1000"),
        available_margin=Decimal("5000"),
        open_positions_count=2,
        max_open_positions=10,
        metadata={"portfolio_id": "demo"},
    )


def test_risk_rule_engine_approves_when_all_rules_pass() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())

    decision = engine.evaluate(_request(), _passing_context())

    assert decision.decision == RiskDecisionResult.APPROVED
    assert decision.approval_id == UUID("00000000-0000-0000-0000-000000000002")
    assert decision.expires_at == FIXED_NOW + timedelta(seconds=30)
    assert decision.is_valid_approval_at(FIXED_NOW + timedelta(seconds=1)) is True
    assert decision.metadata["trading_mode"] == RiskTradingMode.PAPER
    assert "core.quantity-limit" in decision.metadata["passed_rule_ids"]


def test_risk_rule_engine_rejects_by_default_without_explicit_safe_context() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())

    decision = engine.evaluate(_request(), RiskEvaluationContext())

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.approval_id is None
    assert decision.expires_at is None
    assert decision.reason_code == "GLOBAL_HALT_ACTIVE"


def test_live_mode_requires_explicit_enablement() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())
    context = _passing_context()
    live_context = RiskEvaluationContext(
        **{**context.__dict__, "trading_mode": RiskTradingMode.LIVE, "live_trading_enabled": False}
    )

    decision = engine.evaluate(_request(), live_context)

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "LIVE_MODE_DISABLED"
    assert decision.rule_id == "core.live-mode-gate"


def test_quantity_limit_rejects_oversized_order() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())
    context = _passing_context()
    oversized_context = RiskEvaluationContext(
        **{**context.__dict__, "order_quantity": Decimal("101")}
    )

    decision = engine.evaluate(_request(), oversized_context)

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "QUANTITY_LIMIT_EXCEEDED"
    assert decision.rule_id == "core.quantity-limit"


def test_loss_limit_rejects_when_daily_loss_reached() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())
    context = _passing_context()
    loss_context = RiskEvaluationContext(
        **{**context.__dict__, "daily_realized_pnl": Decimal("-1000")}
    )

    decision = engine.evaluate(_request(), loss_context)

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "DAILY_LOSS_LIMIT_EXCEEDED"
    assert decision.rule_id == "core.daily-loss-limit"


def test_duplicate_signal_rejects_before_open_position_limit() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())
    context = _passing_context()
    duplicate_context = RiskEvaluationContext(
        **{
            **context.__dict__,
            "duplicate_signal": True,
            "open_positions_count": 10,
        }
    )

    decision = engine.evaluate(_request(), duplicate_context)

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "DUPLICATE_SIGNAL"
    assert decision.rule_id == "core.duplicate-order-protection"


def test_missing_required_risk_context_rejects_fail_safe() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=_ids())
    context = _passing_context()
    missing_context = RiskEvaluationContext(**{**context.__dict__, "projected_exposure": None})

    decision = engine.evaluate(_request(), missing_context)

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "RISK_CONTEXT_MISSING"
    assert decision.rule_id == "core.exposure-limit"


def test_engine_without_rules_rejects_fail_safe() -> None:
    engine = RiskRuleEngine(rules=(), clock=lambda: FIXED_NOW, id_factory=_ids())

    decision = engine.evaluate(_request(), _passing_context())

    assert decision.decision == RiskDecisionResult.REJECTED
    assert decision.reason_code == "NO_RISK_RULES_CONFIGURED"


def test_risk_rule_engine_exposes_no_broker_order_submission_methods() -> None:
    engine = RiskRuleEngine(clock=lambda: FIXED_NOW, id_factory=uuid4)

    forbidden_names = {
        "broker",
        "broker_credentials",
        "credentials",
        "place_order",
        "submit_order",
        "send_order",
        "execute_order",
    }

    assert forbidden_names.isdisjoint(dir(engine))
