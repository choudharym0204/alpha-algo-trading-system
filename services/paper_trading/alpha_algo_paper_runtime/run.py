from __future__ import annotations

"""Paper run identity (Phase 15).

A ``paper_run_id`` isolates all paper entities (orders, executions, positions,
portfolio, P&L, reconciliation) across separate paper runs. It is deterministic
when seeded (replay) and securely unique otherwise.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4, uuid5


class PaperRunStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    RESET = "RESET"


#: Fixed UUIDv5 namespace for deterministic paper run ids.
PAPER_RUN_NAMESPACE = UUID("7d1f2c3b-4a5e-4f6b-8c9d-0e1f2a3b4c5d")

__all__ = ["PAPER_RUN_NAMESPACE", "PaperRun", "PaperRunStatus", "compute_config_hash", "new_paper_run_id"]


def new_paper_run_id(seed: str | None = None) -> UUID:
    """Deterministic (seeded) or securely unique (unseeded) paper run id."""
    if seed is None:
        return uuid4()
    return uuid5(PAPER_RUN_NAMESPACE, seed)


def compute_config_hash(parts: dict[str, str] | None = None) -> str:
    """Deterministic SHA-256 hash of a run's configuration (replay fingerprint).

    Sorted key/value pairs ensure ordering never affects the fingerprint. A
    None/missing config yields the empty-config digest, not an error.
    """
    parts = parts or {}
    canonical = "&".join(f"{k}={parts[k]}" for k in sorted(parts))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PaperRun:
    """Immutable record of one paper trading run."""

    paper_run_id: UUID
    status: PaperRunStatus
    config_hash: str
    created_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.config_hash.strip():
            raise ValueError("config_hash is required")
        if self.created_at.tzinfo is None or self.created_at.tzinfo.utcoffset(self.created_at) is None:
            raise ValueError("created_at must be timezone-aware")
        if self.completed_at is not None and (
            self.completed_at.tzinfo is None
            or self.completed_at.tzinfo.utcoffset(self.completed_at) is None
        ):
            raise ValueError("completed_at must be timezone-aware")
