"""Approval binding + expiry/reuse validation (Phase 6).

An approval must be unique, time-bounded, traceable, and semantically bound to
the evaluated request so it cannot be safely reused for a different signal,
strategy, version, instrument, action, quantity, account, order type, or
trading mode. The risk identity key doubles as the approval binding so the
idempotency key and the reuse-prevention key are the *same* value.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from alpha_algo_contracts import RiskDecision, RiskDecisionResult, StrategySignal
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_signal_engine.identity import compute_signal_identity_key


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_risk_identity_key(
    signal: StrategySignal,
    intent: RiskOrderIntent | None,
    trading_mode: str,
) -> str:
    """Stable idempotency + approval-binding identity for a risk decision.

    Binds the Phase-5 signal identity to the concrete order intent (quantity,
    account, order type) and trading mode. A replayed signal with a changed
    intent or mode therefore produces a *different* key and is not deduplicated,
    and an approval cannot be reused for a materially different request.
    """
    quantity = intent.quantity if intent is not None else None
    account_id = intent.account_id if intent is not None else None
    order_type = intent.order_type if intent is not None else None
    payload = {
        "signal_identity": compute_signal_identity_key(signal),
        "quantity": str(quantity) if quantity is not None else None,
        "account_id": str(account_id) if account_id is not None else None,
        "order_type": order_type,
        "trading_mode": trading_mode.upper(),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def compute_approval_binding(
    signal: StrategySignal,
    intent: RiskOrderIntent | None,
    trading_mode: str = "PAPER",
) -> str:
    """Backward-compatible alias: the approval binding *is* the risk identity key."""
    return compute_risk_identity_key(signal, intent, trading_mode)


def approval_is_usable(
    decision: RiskDecision,
    now: datetime,
    *,
    binding_hash: str | None = None,
) -> bool:
    """True only if the decision is an unexpired approval bound to ``binding_hash``.

    Fail-closed: an approval without a binding hash, or a caller that omits the
    request binding, is never usable.
    """
    if decision.decision != RiskDecisionResult.APPROVED:
        return False
    if not decision.is_valid_approval_at(now):
        return False
    if decision.binding_hash is None:
        return False
    if binding_hash is None:
        return False
    return decision.binding_hash == binding_hash
