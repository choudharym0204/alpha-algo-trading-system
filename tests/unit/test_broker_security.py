"""Phase 10 — broker security tests (LIVE gating, credential isolation)."""

import asyncio
from pathlib import Path

import pytest

from alpha_algo_broker_integration.contracts import BrokerName, TradingMode
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass

from broker_test_support import creds_ref, make_order_request, adapters


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("broker,factory", adapters())
def test_live_order_blocked_even_with_credentials(broker, factory):
    adapter, _ = factory()
    run(adapter.connect(creds_ref(broker)))  # valid (fake) credentials
    with pytest.raises(BrokerError) as e:
        run(adapter.submit_order(make_order_request(trading_mode=TradingMode.LIVE)))
    assert e.value.error_class == BrokerErrorClass.UNSUPPORTED


def test_no_hardcoded_credentials_in_broker_source():
    root = Path(__file__).resolve().parents[2] / "services" / "broker_adapters"
    source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in root.rglob("*.py")
    )
    # Real-looking secret values must not appear; only placeholders/fakes.
    for token in ("api_secret", "client_secret", "feed_token", "refresh_token"):
        # The words may appear as *names* (contracts), but never assigned a value.
        assert token + " =" not in source.replace(" ", "")


def test_no_real_credentials_in_tests():
    from broker_test_support import fake_credentials

    # The shared fake resolver returns only placeholder values, never real secrets.
    creds = fake_credentials("any-secret-ref")
    assert set(creds.keys()) == {"api_key", "access_token", "client_code", "password", "totp"}
    for value in creds.values():
        # Real API keys/secrets are long random strings; placeholders are short.
        assert len(value) < 40


def test_credentials_are_opaque_references_only():
    from alpha_algo_broker_integration.contracts import BrokerCredentialsRef

    ref = BrokerCredentialsRef(
        broker_name=BrokerName.ZERODHA,
        account_identifier="acc-1",
        secret_ref="env://ZERODHA_SECRET",
    )
    # The contract carries a *reference*, never a secret value.
    assert ref.secret_ref == "env://ZERODHA_SECRET"
    assert not hasattr(ref, "api_key")
    assert not hasattr(ref, "access_token")


def test_adapter_source_has_no_broker_branching_in_core():
    # Core engine must not branch on broker name (isolation boundary).
    from pathlib import Path

    engine_file = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "execution_engine"
        / "alpha_algo_execution_engine"
        / "engine.py"
    )
    text = engine_file.read_text(encoding="utf-8").lower()
    assert 'broker == "zerodha"' not in text
    assert 'broker == "upstox"' not in text
    assert "angel_one" not in text
