"""Phase 6 — concurrency / reserved-quantity race protection.

The risk service is stateless per evaluation: it reads a single coherent
snapshot and evaluates deterministically. Race protection comes from the
snapshot reflecting *reserved/pending* quantities, so two in-flight intents
cannot both be approved against the same base position.
"""

from __future__ import annotations

from decimal import Decimal

from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.service import RiskService

from risk_test_support import healthy_limits, healthy_positions, make_buy_signal, make_snapshot


class ReservedPositionProvider:
    """Simulates an authoritative state source that reserves quantity on approve."""

    def __init__(self, position: Decimal, limit: Decimal) -> None:
        self.position = position
        self.limit = limit
        self.reserved = Decimal("0")

    def get_snapshot(self, *, account_id=None, instrument_id=None, strategy_id=None):
        return make_snapshot(
            positions=healthy_positions(
                position_quantity=self.position,
                projected_position_quantity=None,
                reserved_quantity=self.reserved,
            ),
            limits=healthy_limits(max_position_quantity=self.limit),
        )

    def reserve(self, qty: Decimal) -> None:
        self.reserved += qty


def test_reserved_quantity_prevents_position_limit_race():
    # Position limit = 100, current position = 90.
    provider = ReservedPositionProvider(position=Decimal("90"), limit=Decimal("100"))
    svc = RiskService(provider=provider)

    # Signal A: +10 → projected 90 + 0 reserved + 10 = 100 → approved.
    a = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert a.status == "APPROVED"

    # OMS reserves A's quantity as an open order.
    provider.reserve(Decimal("10"))

    # Signal B: +10 → projected 90 + 10 reserved + 10 = 110 > 100 → rejected.
    b = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert b.status == "REJECTED"
    assert b.decision.reason_code == "POSITION_LIMIT_EXCEEDED"


def test_concurrent_intents_deterministic():
    """Same base state, same intent → identical decision across 'simultaneous' calls."""
    provider = ReservedPositionProvider(position=Decimal("90"), limit=Decimal("100"))
    svc = RiskService(provider=provider)
    results = [
        svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("20")))
        for _ in range(3)
    ]
    codes = [r.decision.reason_code for r in results]
    assert codes == ["POSITION_LIMIT_EXCEEDED"] * 3
