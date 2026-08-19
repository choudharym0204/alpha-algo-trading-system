from __future__ import annotations

import pytest

from alpha_algo_strategy_engine import (
    ConfigValidationError,
    StrategyConfig,
    compute_code_hash,
    compute_config_hash,
    validate_config,
)
from strategy_test_support import make_identity


def test_config_hash_is_deterministic() -> None:
    a = compute_config_hash({"fast": 5, "slow": 20})
    b = compute_config_hash({"slow": 20, "fast": 5})  # key order irrelevant
    assert a == b
    assert compute_config_hash({"fast": 6}) != a


def test_code_hash_is_deterministic() -> None:
    assert compute_code_hash("abc") == compute_code_hash("abc")
    assert compute_code_hash("abc") != compute_code_hash("abd")


def test_identity_rejects_blank_fields() -> None:
    import pytest

    with pytest.raises(ValueError):
        make_identity(code="")
    with pytest.raises(ValueError):
        make_identity(version="   ")


def test_validate_config_rejects_non_mapping() -> None:
    with pytest.raises(ConfigValidationError):
        validate_config("not-a-mapping")  # type: ignore[arg-type]


def test_validate_config_rejects_non_string_key() -> None:
    with pytest.raises(ConfigValidationError):
        validate_config({1: "x"})  # type: ignore[dict-item]


def test_validate_config_rejects_unserializable_value() -> None:
    with pytest.raises(ConfigValidationError):
        validate_config({"bad": object()})


def test_validate_config_enforces_required_keys() -> None:
    with pytest.raises(ConfigValidationError):
        validate_config({"a": 1}, required_keys={"a", "b"})


def test_strategy_config_is_immutable_and_hashes() -> None:
    config = StrategyConfig(values={"fast": 5, "slow": 20})
    assert config.config_hash == compute_config_hash({"fast": 5, "slow": 20})
    with pytest.raises(TypeError):
        config.values["fast"] = 99  # MappingProxyType is read-only
