from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alpha_algo_contracts import SignalAction, StrategySignal, StrategyVersion


def test_strategy_version_requires_auditable_identity() -> None:
    strategy_id = uuid4()

    version = StrategyVersion(
        strategy_id=strategy_id,
        version="2.3.0",
        config_hash="sha256:config",
        code_hash="sha256:code",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        metadata={"source": "unit-test"},
    )

    assert version.strategy_id == strategy_id
    assert version.version == "2.3.0"
    assert version.config_hash == "sha256:config"


def test_strategy_version_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        StrategyVersion(
            strategy_id=uuid4(),
            version="2.3.0",
            config_hash="sha256:config",
            created_at=datetime(2026, 1, 1),
        )


def test_strategy_signal_contains_required_audit_fields() -> None:
    signal_id = uuid4()
    strategy_id = uuid4()

    signal = StrategySignal(
        signal_id=signal_id,
        strategy_id=strategy_id,
        strategy_version="2.3.0",
        strategy_config_hash="sha256:config",
        instrument_id=uuid4(),
        action=SignalAction.SELL,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        confidence=Decimal("0.65"),
        reason="mean reversion threshold",
        metadata={"window": 20},
    )

    assert signal.audit_key == f"{strategy_id}:2.3.0:sha256:config:{signal_id}"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("strategy_version", " "),
        ("strategy_config_hash", " "),
        ("reason", " "),
    ],
)
def test_strategy_signal_rejects_blank_required_text(field_name: str, value: str) -> None:
    payload = {
        "strategy_id": uuid4(),
        "strategy_version": "2.3.0",
        "strategy_config_hash": "sha256:config",
        "instrument_id": uuid4(),
        "action": SignalAction.BUY,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "confidence": Decimal("0.5"),
        "reason": "valid reason",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        StrategySignal(**payload)


@pytest.mark.parametrize("confidence", [Decimal("-0.01"), Decimal("1.01")])
def test_strategy_signal_rejects_out_of_range_confidence(confidence: Decimal) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        StrategySignal(
            strategy_id=uuid4(),
            strategy_version="2.3.0",
            strategy_config_hash="sha256:config",
            instrument_id=uuid4(),
            action=SignalAction.HOLD,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            confidence=confidence,
            reason="flat market",
        )


def test_strategy_signal_is_advisory_and_has_no_order_or_broker_fields() -> None:
    contract_fields = set(StrategySignal.model_fields)

    assert {
        "order_id",
        "broker_order_id",
        "risk_approval_id",
        "broker_credentials",
        "credentials",
    }.isdisjoint(contract_fields)
