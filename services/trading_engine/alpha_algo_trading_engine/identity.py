"""Deterministic orchestration identity (Phase 7).

Idempotency is keyed on a stable identity derived from the signal identity, the
strategy run, the concrete order intent (quantity/account/order type), and the
trading mode. It is *not* derived from random UUIDs, so a replayed or retried
delivery of the same accepted signal cannot mint a second downstream intent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from alpha_algo_contracts import StrategySignal
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_signal_engine.identity import (
    compute_signal_identity_key,
    run_id_from,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_orchestration_identity_key(
    signal: StrategySignal,
    intent: RiskOrderIntent | None,
    trading_mode: str,
) -> str:
    quantity = intent.quantity if intent is not None else None
    account_id = intent.account_id if intent is not None else None
    order_type = intent.order_type if intent is not None else None
    payload = {
        "signal_identity": compute_signal_identity_key(signal),
        "strategy_run_id": run_id_from(signal),
        "quantity": str(quantity) if quantity is not None else None,
        "account_id": str(account_id) if account_id is not None else None,
        "order_type": order_type,
        "trading_mode": trading_mode.upper(),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
