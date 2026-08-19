from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_strategy_engine import SignalValidator, StrategyRuntime, TradingMode
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
    make_tick,
)


def _validator(now: datetime | None = None):
    now = now or datetime.now(UTC)
    return SignalValidator(clock=lambda: now, future_skew=timedelta(seconds=5))


def test_valid_signal_passes() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=identity.strategy_id, version="1.0.0", config_hash=identity.config_hash
    )
    assert _validator().validate(signal, identity).valid is True


def test_wrong_strategy_id_rejected() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=uuid4(), version="1.0.0", config_hash=identity.config_hash
    )
    assert _validator().validate(signal, identity).reason == "strategy_id_mismatch"


def test_wrong_version_rejected() -> None:
    identity = make_identity(version="1.0.0")
    signal = make_signal(
        strategy_id=identity.strategy_id, version="2.0.0", config_hash=identity.config_hash
    )
    assert _validator().validate(signal, identity).reason == "strategy_version_mismatch"


def test_wrong_config_hash_rejected() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=identity.strategy_id, version="1.0.0", config_hash="deadbeef"
    )
    assert _validator().validate(signal, identity).reason == "config_hash_mismatch"


def test_future_timestamp_rejected() -> None:
    identity = make_identity()
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)
    signal = make_signal(
        strategy_id=identity.strategy_id,
        version="1.0.0",
        config_hash=identity.config_hash,
        timestamp=now + timedelta(seconds=10),
    )
    assert _validator(now).validate(signal, identity).reason == "future_timestamp"


def test_unsubscribed_instrument_rejected() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=identity.strategy_id,
        version="1.0.0",
        config_hash=identity.config_hash,
        instrument_id=uuid4(),
    )
    result = _validator().validate(signal, identity, allowed_instruments={uuid4()})
    assert result.reason == "instrument_not_subscribed"


def test_invalid_action_rejected_by_contract() -> None:
    identity = make_identity()
    with pytest.raises(ValidationError):
        StrategySignal(
            strategy_id=identity.strategy_id,
            strategy_version="1.0.0",
            strategy_config_hash=identity.config_hash,
            instrument_id=uuid4(),
            action="BOGUS",  # type: ignore[arg-type]
            timestamp=datetime.now(UTC),
            confidence=Decimal("0.8"),
            reason="test",
        )


def test_confidence_boundary() -> None:
    identity = make_identity()

    def sig(conf: str) -> StrategySignal:
        return StrategySignal(
            strategy_id=identity.strategy_id,
            strategy_version="1.0.0",
            strategy_config_hash=identity.config_hash,
            instrument_id=uuid4(),
            action=SignalAction.BUY,
            timestamp=datetime.now(UTC),
            confidence=Decimal(conf),
            reason="test",
        )

    assert sig("0").confidence == Decimal("0")
    assert sig("1").confidence == Decimal("1")
    with pytest.raises(ValidationError):
        sig("-0.1")
    with pytest.raises(ValidationError):
        sig("1.1")


def test_missing_reason_rejected() -> None:
    identity = make_identity()
    with pytest.raises(ValidationError):
        StrategySignal(
            strategy_id=identity.strategy_id,
            strategy_version="1.0.0",
            strategy_config_hash=identity.config_hash,
            instrument_id=uuid4(),
            action=SignalAction.BUY,
            timestamp=datetime.now(UTC),
            confidence=Decimal("0.8"),
            reason="   ",
        )


def test_runtime_enriches_accepted_signal_for_traceability() -> None:
    identity = make_identity()
    instr = uuid4()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version="1.0.0",
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]
    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    signals = runtime.on_tick(make_tick(instrument_id=instr))
    assert len(signals) == 1
    enriched = signals[0]
    assert enriched.metadata["strategy_code_hash"] == identity.code_hash
    assert enriched.metadata["strategy_run_id"] is not None
    assert "event_timestamp" in enriched.metadata
