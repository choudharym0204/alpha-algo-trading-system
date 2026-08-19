"""Strategy identity + deterministic hashing (config hash / code hash)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID


def _require_non_blank(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} cannot be blank")
    return value


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization (sorted keys) for reproducible hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_config_hash(config: Mapping[str, object]) -> str:
    """Deterministic SHA-256 over the canonical form of a configuration."""
    return hashlib.sha256(canonical_json(dict(config)).encode("utf-8")).hexdigest()


def compute_code_hash(code_source: str) -> str:
    """Deterministic SHA-256 over strategy source/code bytes."""
    return hashlib.sha256(code_source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StrategyIdentity:
    """Stable identity: who + which version + which config + which code."""

    strategy_id: UUID
    code: str
    name: str
    version: str
    config_hash: str
    code_hash: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.code, "code")
        _require_non_blank(self.name, "name")
        _require_non_blank(self.version, "version")
        _require_non_blank(self.config_hash, "config_hash")
        if self.code_hash is not None:
            _require_non_blank(self.code_hash, "code_hash")
