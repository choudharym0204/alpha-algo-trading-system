from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Callable, Protocol
from uuid import UUID, uuid4

from alpha_algo_contracts import (
    RiskAssessmentRequest,
    RiskDecision,
    RiskDecisionResult,
)


class RiskTradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass(frozen=True)
class RiskEvaluationContext:
    trading_mode: RiskTradingMode = RiskTradingMode.LIVE
    live_trading_enabled: bool = False
    global_halt_active: bool = True
    broker_connected: bool = False
    market_data_fresh: bool = False
    market_session_open: bool = False
    instrument_allowed: bool = False
    duplicate_signal: bool = True
    order_quantity: Decimal | None = None
    max_order_quantity: Decimal | None = None
    projected_position_quantity: Decimal | None = None
    max_position_quantity: Decimal | None = None
    projected_exposure: Decimal | None = None
    max_exposure: Decimal | None = None
    daily_realized_pnl: Decimal | None = None
    max_daily_loss: Decimal | None = None
    strategy_realized_pnl: Decimal | None = None
    max_strategy_loss: Decimal | None = None
    required_margin: Decimal | None = None
    available_margin: Decimal | None = None
    open_positions_count: int | None = None
    max_open_positions: int | None = None
    # --- Phase 6 runtime additions (configurable controls: inactive when a
    # limit is not configured; fail-closed when configured but the measured
    # value is missing) ---
    equity_value: Decimal | None = None
    high_water_mark: Decimal | None = None
    current_drawdown: Decimal | None = None
    max_drawdown: Decimal | None = None
    reference_price: Decimal | None = None
    current_price: Decimal | None = None
    max_price_deviation: Decimal | None = None
    recent_order_count: int | None = None
    max_orders_per_window: int | None = None
    order_window_seconds: int | None = None
    account_max_order_quantity: Decimal | None = None
    account_max_positions: int | None = None
    account_max_exposure: Decimal | None = None
    account_max_loss: Decimal | None = None
    account_max_order_rate: int | None = None
    account_daily_realized_pnl: Decimal | None = None
    pending_execution_count: int | None = None
    max_unresolved_executions: int | None = None
    retry_count: int | None = None
    max_retries_per_signal: int | None = None
    reserved_quantity: Decimal | None = None
    open_order_quantity: Decimal | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleEvaluation:
    passed: bool
    rule_id: str
    reason_code: str
    reason: str
    metadata: dict[str, object] = field(default_factory=dict)


class RiskRule(Protocol):
    rule_id: str

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        ...


def _pass(rule_id: str) -> RuleEvaluation:
    return RuleEvaluation(
        passed=True,
        rule_id=rule_id,
        reason_code="PASSED",
        reason="rule passed",
    )


def _reject(rule_id: str, reason_code: str, reason: str) -> RuleEvaluation:
    return RuleEvaluation(
        passed=False,
        rule_id=rule_id,
        reason_code=reason_code,
        reason=reason,
    )


def _require_positive_pair(
    *,
    rule_id: str,
    current_value: Decimal | None,
    limit_value: Decimal | None,
    current_name: str,
    limit_name: str,
) -> RuleEvaluation | None:
    if current_value is None or limit_value is None:
        return _reject(
            rule_id,
            "RISK_CONTEXT_MISSING",
            f"{current_name} and {limit_name} are required",
        )
    if current_value < Decimal("0") or limit_value <= Decimal("0"):
        return _reject(
            rule_id,
            "RISK_CONTEXT_INVALID",
            f"{current_name} must be non-negative and {limit_name} must be positive",
        )
    return None


class GlobalHaltRule:
    rule_id = "core.global-halt"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.global_halt_active:
            return _reject(self.rule_id, "GLOBAL_HALT_ACTIVE", "global trading halt is active")
        return _pass(self.rule_id)


class LiveModeRule:
    rule_id = "core.live-mode-gate"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.trading_mode == RiskTradingMode.LIVE and not context.live_trading_enabled:
            return _reject(
                self.rule_id,
                "LIVE_MODE_DISABLED",
                "LIVE trading is not explicitly enabled",
            )
        return _pass(self.rule_id)


class BrokerHealthRule:
    rule_id = "core.broker-health"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if not context.broker_connected:
            return _reject(self.rule_id, "BROKER_DISCONNECTED", "broker connection is not healthy")
        return _pass(self.rule_id)


class MarketDataFreshnessRule:
    rule_id = "core.market-data-freshness"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if not context.market_data_fresh:
            return _reject(self.rule_id, "STALE_MARKET_DATA", "market data is stale or unavailable")
        return _pass(self.rule_id)


class MarketSessionRule:
    rule_id = "core.market-session"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if not context.market_session_open:
            return _reject(self.rule_id, "MARKET_SESSION_CLOSED", "market session is closed")
        return _pass(self.rule_id)


class InstrumentRestrictionRule:
    rule_id = "core.instrument-restriction"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if not context.instrument_allowed:
            return _reject(self.rule_id, "INSTRUMENT_BLOCKED", "instrument is not allowed")
        return _pass(self.rule_id)


class QuantityLimitRule:
    rule_id = "core.quantity-limit"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        missing = _require_positive_pair(
            rule_id=self.rule_id,
            current_value=context.order_quantity,
            limit_value=context.max_order_quantity,
            current_name="order_quantity",
            limit_name="max_order_quantity",
        )
        if missing is not None:
            return missing
        if context.order_quantity == Decimal("0"):
            return _reject(self.rule_id, "ZERO_QUANTITY", "order quantity must be positive")
        if context.order_quantity > context.max_order_quantity:
            return _reject(self.rule_id, "QUANTITY_LIMIT_EXCEEDED", "order quantity exceeds limit")
        return _pass(self.rule_id)


class PositionLimitRule:
    rule_id = "core.position-limit"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        missing = _require_positive_pair(
            rule_id=self.rule_id,
            current_value=abs(context.projected_position_quantity)
            if context.projected_position_quantity is not None
            else None,
            limit_value=context.max_position_quantity,
            current_name="projected_position_quantity",
            limit_name="max_position_quantity",
        )
        if missing is not None:
            return missing
        if abs(context.projected_position_quantity) > context.max_position_quantity:
            return _reject(self.rule_id, "POSITION_LIMIT_EXCEEDED", "projected position exceeds limit")
        return _pass(self.rule_id)


class ExposureLimitRule:
    rule_id = "core.exposure-limit"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        missing = _require_positive_pair(
            rule_id=self.rule_id,
            current_value=context.projected_exposure,
            limit_value=context.max_exposure,
            current_name="projected_exposure",
            limit_name="max_exposure",
        )
        if missing is not None:
            return missing
        if context.projected_exposure > context.max_exposure:
            return _reject(self.rule_id, "EXPOSURE_LIMIT_EXCEEDED", "projected exposure exceeds limit")
        return _pass(self.rule_id)


class DailyLossLimitRule:
    rule_id = "core.daily-loss-limit"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.daily_realized_pnl is None or context.max_daily_loss is None:
            return _reject(
                self.rule_id,
                "RISK_CONTEXT_MISSING",
                "daily_realized_pnl and max_daily_loss are required",
            )
        if context.max_daily_loss <= Decimal("0"):
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "max_daily_loss must be positive")
        if context.daily_realized_pnl <= -context.max_daily_loss:
            return _reject(self.rule_id, "DAILY_LOSS_LIMIT_EXCEEDED", "daily loss limit reached")
        return _pass(self.rule_id)


class StrategyLossLimitRule:
    rule_id = "core.strategy-loss-limit"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.strategy_realized_pnl is None or context.max_strategy_loss is None:
            return _reject(
                self.rule_id,
                "RISK_CONTEXT_MISSING",
                "strategy_realized_pnl and max_strategy_loss are required",
            )
        if context.max_strategy_loss <= Decimal("0"):
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "max_strategy_loss must be positive")
        if context.strategy_realized_pnl <= -context.max_strategy_loss:
            return _reject(self.rule_id, "STRATEGY_LOSS_LIMIT_EXCEEDED", "strategy loss limit reached")
        return _pass(self.rule_id)


class MarginAvailabilityRule:
    rule_id = "core.margin-availability"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        missing = _require_positive_pair(
            rule_id=self.rule_id,
            current_value=context.required_margin,
            limit_value=context.available_margin,
            current_name="required_margin",
            limit_name="available_margin",
        )
        if missing is not None:
            return missing
        if context.required_margin > context.available_margin:
            return _reject(self.rule_id, "MARGIN_UNAVAILABLE", "required margin exceeds availability")
        return _pass(self.rule_id)


class DuplicateOrderProtectionRule:
    rule_id = "core.duplicate-order-protection"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.duplicate_signal:
            return _reject(self.rule_id, "DUPLICATE_SIGNAL", "duplicate signal detected")
        return _pass(self.rule_id)


class MaximumOpenPositionsRule:
    rule_id = "core.maximum-open-positions"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.open_positions_count is None or context.max_open_positions is None:
            return _reject(
                self.rule_id,
                "RISK_CONTEXT_MISSING",
                "open_positions_count and max_open_positions are required",
            )
        if context.open_positions_count < 0 or context.max_open_positions < 0:
            return _reject(
                self.rule_id,
                "RISK_CONTEXT_INVALID",
                "open position counts must be non-negative",
            )
        if context.open_positions_count >= context.max_open_positions:
            return _reject(
                self.rule_id,
                "MAX_OPEN_POSITIONS_REACHED",
                "maximum simultaneous positions reached",
            )
        return _pass(self.rule_id)


class AccountLimitRule:
    """Account-level limits, evaluated independently of strategy-level limits.

    Each sub-check is active only when its account limit is configured; a
    configured limit with a missing measured value fails closed.
    """

    rule_id = "core.account-limits"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.account_max_order_quantity is not None:
            if context.order_quantity is None:
                return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "order_quantity is required for the account quantity limit")
            if context.order_quantity > context.account_max_order_quantity:
                return _reject(self.rule_id, "ACCOUNT_ORDER_QUANTITY_LIMIT_EXCEEDED", "account order-quantity limit exceeded")
        if context.account_max_positions is not None:
            if context.open_positions_count is None:
                return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "open_positions_count is required for the account position limit")
            if context.open_positions_count >= context.account_max_positions:
                return _reject(self.rule_id, "ACCOUNT_POSITIONS_LIMIT_EXCEEDED", "account position limit reached")
        if context.account_max_exposure is not None:
            if context.projected_exposure is None:
                return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "projected_exposure is required for the account exposure limit")
            if context.projected_exposure > context.account_max_exposure:
                return _reject(self.rule_id, "ACCOUNT_EXPOSURE_LIMIT_EXCEEDED", "account exposure limit exceeded")
        if context.account_max_loss is not None:
            if context.account_daily_realized_pnl is None:
                return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "account_daily_realized_pnl is required for the account loss limit")
            if context.account_daily_realized_pnl <= -context.account_max_loss:
                return _reject(self.rule_id, "ACCOUNT_LOSS_LIMIT_EXCEEDED", "account loss limit reached")
        if context.account_max_order_rate is not None:
            if context.recent_order_count is None:
                return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "recent_order_count is required for the account order-rate limit")
            if context.recent_order_count >= context.account_max_order_rate:
                return _reject(self.rule_id, "ACCOUNT_ORDER_RATE_EXCEEDED", "account order-rate limit exceeded")
        return _pass(self.rule_id)


class MaximumDrawdownRule:
    rule_id = "core.maximum-drawdown"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.max_drawdown is None:
            return _pass(self.rule_id)  # control not configured
        if context.current_drawdown is None:
            return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "current_drawdown is required when a drawdown limit is configured")
        if context.max_drawdown < 0 or context.current_drawdown < 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "drawdown values must be non-negative")
        if context.current_drawdown > context.max_drawdown:
            return _reject(self.rule_id, "DRAWDOWN_LIMIT_EXCEEDED", "drawdown limit exceeded")
        return _pass(self.rule_id)


class PriceDeviationRule:
    rule_id = "core.price-deviation"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.max_price_deviation is None:
            return _pass(self.rule_id)  # control not configured
        if context.reference_price is None or context.current_price is None:
            return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "reference_price and current_price are required when a price-deviation limit is configured")
        if context.reference_price <= 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "reference_price must be positive")
        if context.current_price <= 0:
            return _reject(self.rule_id, "PRICE_INVALID", "current price must be positive")
        if context.max_price_deviation < 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "max_price_deviation must be non-negative")
        deviation = abs(context.current_price - context.reference_price) / context.reference_price
        if deviation > context.max_price_deviation:
            return _reject(self.rule_id, "PRICE_DEVIATION_EXCEEDED", "price deviation from reference exceeds threshold")
        return _pass(self.rule_id)


class OrderFrequencyRule:
    rule_id = "core.order-frequency"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.max_orders_per_window is None:
            return _pass(self.rule_id)  # control not configured
        if context.recent_order_count is None:
            return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "recent_order_count is required when an order-frequency limit is configured")
        if context.recent_order_count < 0 or context.max_orders_per_window < 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "order counts must be non-negative")
        if context.recent_order_count >= context.max_orders_per_window:
            return _reject(self.rule_id, "ORDER_FREQUENCY_LIMIT_EXCEEDED", "order frequency limit reached")
        return _pass(self.rule_id)


class ExecutionTimeoutRule:
    rule_id = "core.execution-timeout"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.max_unresolved_executions is None:
            return _pass(self.rule_id)  # control not configured
        if context.pending_execution_count is None:
            return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "pending_execution_count is required when an execution-timeout limit is configured")
        if context.pending_execution_count < 0 or context.max_unresolved_executions < 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "execution counts must be non-negative")
        if context.pending_execution_count >= context.max_unresolved_executions:
            return _reject(self.rule_id, "UNRESOLVED_EXECUTIONS_LIMIT_EXCEEDED", "too many unresolved executions")
        return _pass(self.rule_id)


class RetrySafetyRule:
    rule_id = "core.retry-safety"

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RuleEvaluation:
        if context.max_retries_per_signal is None:
            return _pass(self.rule_id)  # control not configured
        if context.retry_count is None:
            return _reject(self.rule_id, "RISK_CONTEXT_MISSING", "retry_count is required when a retry limit is configured")
        if context.retry_count < 0 or context.max_retries_per_signal < 0:
            return _reject(self.rule_id, "RISK_CONTEXT_INVALID", "retry counts must be non-negative")
        if context.retry_count > context.max_retries_per_signal:
            return _reject(self.rule_id, "MAX_RETRIES_EXCEEDED", "signal retry limit exceeded")
        return _pass(self.rule_id)


def default_risk_rules() -> tuple[RiskRule, ...]:
    return (
        GlobalHaltRule(),
        LiveModeRule(),
        BrokerHealthRule(),
        MarketDataFreshnessRule(),
        MarketSessionRule(),
        InstrumentRestrictionRule(),
        AccountLimitRule(),
        QuantityLimitRule(),
        PositionLimitRule(),
        ExposureLimitRule(),
        DailyLossLimitRule(),
        StrategyLossLimitRule(),
        MarginAvailabilityRule(),
        MaximumDrawdownRule(),
        PriceDeviationRule(),
        OrderFrequencyRule(),
        DuplicateOrderProtectionRule(),
        MaximumOpenPositionsRule(),
        ExecutionTimeoutRule(),
        RetrySafetyRule(),
    )


class RiskRuleEngine:
    def __init__(
        self,
        rules: tuple[RiskRule, ...] | None = None,
        *,
        approval_ttl: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if approval_ttl <= timedelta(0):
            raise ValueError("approval_ttl must be positive")
        self._rules = self._with_global_halt_first(rules)
        self._approval_ttl = approval_ttl
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._id_factory = id_factory

    @staticmethod
    def _with_global_halt_first(
        rules: tuple[RiskRule, ...] | None,
    ) -> tuple[RiskRule, ...]:
        """Guarantee the global halt rule runs first (un-overridable).

        An empty rule set is preserved (the engine rejects with
        ``NO_RISK_RULES_CONFIGURED``); any non-empty set is normalized so a
        ``GlobalHaltRule`` is present and first, regardless of what the caller
        injected.
        """
        if rules is None:
            return default_risk_rules()
        resolved = tuple(rules)
        if not resolved:
            return resolved
        if isinstance(resolved[0], GlobalHaltRule):
            return resolved
        without_halt = tuple(r for r in resolved if not isinstance(r, GlobalHaltRule))
        return (GlobalHaltRule(),) + without_halt

    def evaluate(
        self,
        request: RiskAssessmentRequest,
        context: RiskEvaluationContext,
    ) -> RiskDecision:
        evaluated_at = self._clock()
        if evaluated_at.tzinfo is None or evaluated_at.tzinfo.utcoffset(evaluated_at) is None:
            raise ValueError("clock must return a timezone-aware datetime")

        if not self._rules:
            return self._reject(
                request=request,
                evaluated_at=evaluated_at,
                rule_id="core.fail-safe",
                reason_code="NO_RISK_RULES_CONFIGURED",
                reason="risk engine has no configured rules",
                metadata={"context": context.metadata},
            )

        passed_rule_ids: list[str] = []
        for rule in self._rules:
            try:
                result = rule.evaluate(request, context)
            except Exception as exc:  # pragma: no cover - concrete behavior tested through a failing rule.
                return self._reject(
                    request=request,
                    evaluated_at=evaluated_at,
                    rule_id=getattr(rule, "rule_id", "core.unknown-rule"),
                    reason_code="RISK_RULE_ERROR",
                    reason="risk rule raised an exception",
                    metadata={"error_type": type(exc).__name__, "context": context.metadata},
                )

            if not result.passed:
                return self._reject(
                    request=request,
                    evaluated_at=evaluated_at,
                    rule_id=result.rule_id,
                    reason_code=result.reason_code,
                    reason=result.reason,
                    metadata={**result.metadata, "passed_rule_ids": passed_rule_ids},
                )
            passed_rule_ids.append(result.rule_id)

        return RiskDecision(
            decision_id=self._id_factory(),
            request_id=request.request_id,
            signal_id=request.signal.signal_id,
            strategy_id=request.signal.strategy_id,
            instrument_id=request.signal.instrument_id,
            decision=RiskDecisionResult.APPROVED,
            reason_code="ALL_RULES_PASSED",
            reason="all configured risk rules passed",
            rule_id="core.risk-rule-engine",
            evaluated_at=evaluated_at,
            approval_id=self._id_factory(),
            expires_at=evaluated_at + self._approval_ttl,
            metadata={
                "passed_rule_ids": passed_rule_ids,
                "context": context.metadata,
                "trading_mode": context.trading_mode,
            },
        )

    def _reject(
        self,
        *,
        request: RiskAssessmentRequest,
        evaluated_at: datetime,
        rule_id: str,
        reason_code: str,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> RiskDecision:
        return RiskDecision(
            decision_id=self._id_factory(),
            request_id=request.request_id,
            signal_id=request.signal.signal_id,
            strategy_id=request.signal.strategy_id,
            instrument_id=request.signal.instrument_id,
            decision=RiskDecisionResult.REJECTED,
            reason_code=reason_code,
            reason=reason,
            rule_id=rule_id,
            evaluated_at=evaluated_at,
            metadata=metadata or {},
        )
