from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_broker_adapters import (
    BrokerAdapter,
    BrokerCapabilities,
    BrokerOrderRequest,
    OrderSide,
    OrderType,
    TradingMode,
)


def test_broker_adapter_contract_is_async_protocol() -> None:
    required_methods = {
        "connect",
        "disconnect",
        "get_quote",
        "submit_order",
        "cancel_order",
        "get_positions",
    }

    for method_name in required_methods:
        assert inspect.iscoroutinefunction(getattr(BrokerAdapter, method_name))


def test_broker_capabilities_disable_live_trading_by_default() -> None:
    capabilities = BrokerCapabilities(
        broker_name="example",
        supports_market_data=True,
        supports_order_submission=True,
        supports_order_cancel=True,
        supports_positions=True,
    )

    assert capabilities.supports_live_trading is False


def test_order_request_requires_risk_approval_and_mode() -> None:
    request = BrokerOrderRequest(
        broker_account_id=uuid4(),
        instrument_id=uuid4(),
        trading_mode=TradingMode.PAPER,
        client_order_id="client-1",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        risk_approval_id="risk-approval-1",
        limit_price=Decimal("100.50"),
        metadata={"created_at": datetime.now(UTC).isoformat()},
    )

    assert request.trading_mode == TradingMode.PAPER
    assert request.risk_approval_id == "risk-approval-1"
    assert request.metadata["created_at"]

