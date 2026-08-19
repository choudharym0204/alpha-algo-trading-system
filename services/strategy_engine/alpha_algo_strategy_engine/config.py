"""Controlled, validated, immutable strategy configuration."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from alpha_algo_strategy_engine.errors import ConfigValidationError
from alpha_algo_strategy_engine.identity import compute_config_hash

_JSON_SCALARS = (str, int, float, bool, type(None))


def _is_json_value(value: Any) -> bool:
    if isinstance(value, _JSON_SCALARS):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_value(v) for k, v in value.items())
    # Decimal is not natively JSON-serializable but is common in this domain;
    # canonical_json uses default=str so Decimal is acceptable as a scalar.
    if hasattr(value, "as_integer_ratio") or isinstance(value, (bytes,)):
        return False
    return True


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze dict/list structures so nested values cannot mutate."""
    if isinstance(value, dict):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(v) for v in value)
    return value


def validate_config(
    values: Mapping[str, object],
    *,
    required_keys: set[str] | None = None,
) -> Mapping[str, object]:
    """Validate a config mapping and return a frozen copy.

    Rejects non-mappings, non-string keys, and non-JSON-serializable values so
    the config is always reproducible and hashable.
    """
    if not isinstance(values, Mapping):
        raise ConfigValidationError("config must be a mapping")
    for key in values:
        if not isinstance(key, str):
            raise ConfigValidationError(f"config keys must be strings, got {key!r}")
        try:
            json.dumps(values[key], sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(f"config value for {key!r} is not serializable") from exc
    if required_keys is not None:
        missing = required_keys - set(values)
        if missing:
            raise ConfigValidationError(f"missing required config keys: {sorted(missing)}")
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable, versioned config: values + derived config hash.

    Values are validated, deep-copied (so the instance never shares mutable
    references with the caller), and deep-frozen (nested dicts become read-only
    mappings and nested lists become tuples).
    """

    values: Mapping[str, object]
    config_hash: str | None = None

    def __post_init__(self) -> None:
        validate_config(self.values)
        if self.config_hash is None:
            object.__setattr__(self, "config_hash", compute_config_hash(self.values))
        elif not self.config_hash.strip():
            raise ConfigValidationError("config_hash cannot be blank")
        # Deep-copy + deep-freeze so the config cannot be mutated (nested or top
        # level) after construction, and the hash stays authoritative.
        owned = {k: deepcopy(v) for k, v in self.values.items()}
        object.__setattr__(self, "values", MappingProxyType(_deep_freeze(owned)))
