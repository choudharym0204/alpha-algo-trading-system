from __future__ import annotations

import pytest

from alpha_algo_api.config import Settings


def test_market_data_defaults_are_fail_closed() -> None:
    s = Settings(_env_file=None)
    assert s.market_data_enabled is False
    assert s.market_data_provider == "fake"
    assert s.market_data_stale_after_seconds == 5
    assert s.market_data_reconnect_max_attempts == 10
    assert s.market_data_backpressure_queue_size == 10000
    assert s.market_data_drop_policy == "drop_newest"
    assert s.market_data_persist_enabled is True


def test_market_data_symbol_list_parses_commas() -> None:
    s = Settings(_env_file=None, market_data_symbols="RELIANCE, INFY,TCS")
    assert s.market_data_symbol_list == ["RELIANCE", "INFY", "TCS"]


def test_stale_after_seconds_must_be_positive() -> None:
    with pytest.raises(ValueError, match="market_data_stale_after_seconds"):
        Settings(_env_file=None, market_data_stale_after_seconds=0)


def test_reconnect_max_attempts_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="market_data_reconnect_max_attempts"):
        Settings(_env_file=None, market_data_reconnect_max_attempts=-1)


def test_queue_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="market_data_backpressure_queue_size"):
        Settings(_env_file=None, market_data_backpressure_queue_size=0)


def test_drop_policy_must_be_valid() -> None:
    with pytest.raises(ValueError, match="market_data_drop_policy"):
        Settings(_env_file=None, market_data_drop_policy="bogus")
