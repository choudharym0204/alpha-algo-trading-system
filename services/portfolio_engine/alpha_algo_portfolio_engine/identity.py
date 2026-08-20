"""Deterministic portfolio + snapshot identity (Phase 12).

* ``PortfolioIdentity`` — canonical portfolio key = **(broker_account_id,
  trading_mode)**. This preserves the existing ``portfolio_snapshots`` unique
  constraint on ``(broker_account_id, trading_mode, snapshot_at)``: a portfolio
  is account- + mode-scoped; snapshots are time-indexed states of it.

* ``snapshot_content_hash`` — SHA-256 over a computation's mutable aggregate
  payload, used for idempotency/conflict observability (stored in the snapshot
  payload, never as a primary key).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from alpha_algo_portfolio_engine.contracts import PortfolioIdentity


def compute_portfolio_key(*, account_id: UUID, trading_mode: str) -> str:
    """Deterministic string key for the canonical (account, mode) portfolio."""
    return f"{account_id}:{trading_mode.upper()}"


def build_portfolio_identity(*, account_id: UUID, trading_mode: str) -> PortfolioIdentity:
    return PortfolioIdentity(account_id=account_id, trading_mode=trading_mode.upper())


def compute_snapshot_key(
    *, account_id: UUID, trading_mode: str, snapshot_at: datetime
) -> str:
    """Deterministic snapshot identity (account + mode + snapshot timestamp)."""
    return (
        f"{account_id}:{trading_mode.upper()}:"
        f"{snapshot_at.isoformat()}"
    )


def snapshot_content_hash(
    *,
    account_id: UUID,
    trading_mode: str,
    snapshot_at: datetime,
    gross_exposure: str,
    net_exposure: str,
    long_exposure: str,
    short_exposure: str,
    market_value: str | None,
    cash_balance: str | None,
    position_count: int,
) -> str:
    """Deterministic content hash of a snapshot's aggregate payload."""
    payload = {
        "account_id": str(account_id),
        "trading_mode": trading_mode.upper(),
        "snapshot_at": snapshot_at.isoformat(),
        "gross_exposure": gross_exposure,
        "net_exposure": net_exposure,
        "long_exposure": long_exposure,
        "short_exposure": short_exposure,
        "market_value": market_value,
        "cash_balance": cash_balance,
        "position_count": position_count,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
