"""Shared helpers for Phase 12 portfolio-engine tests (not a test module)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_portfolio_engine.contracts import (
    FundsState,
    PortfolioInputs,
    PortfolioSnapshot,
    PositionInput,
    ReferencePrice,
)
from alpha_algo_portfolio_engine.errors import (
    DuplicateSnapshotError,
    PortfolioPersistenceError,
)


def make_position(
    *,
    instrument_id: UUID | None = None,
    strategy_run_id: UUID | None = None,
    quantity: int = 100,
    average_price: str | Decimal | None = "100",
    status: str = "OPEN",
    position_id: UUID | None = None,
) -> PositionInput:
    return PositionInput(
        position_id=position_id or uuid4(),
        instrument_id=instrument_id or uuid4(),
        strategy_run_id=strategy_run_id or uuid4(),
        quantity=quantity,
        average_price=Decimal(average_price) if average_price is not None else None,
        status=status,
    )


def make_price(
    instrument_id: UUID,
    price: str | Decimal = "100",
    *,
    observed_at: datetime | None = None,
) -> ReferencePrice:
    return ReferencePrice(
        instrument_id=instrument_id,
        price=Decimal(price),
        observed_at=observed_at or datetime.now(UTC),
    )


def make_funds(
    *,
    available_cash: str | Decimal | None = "1000000",
    available_margin: str | Decimal | None = "800000",
    used_margin: str | Decimal | None = "200000",
    captured_at: datetime | None = None,
) -> FundsState:
    return FundsState(
        available_cash=Decimal(available_cash) if available_cash is not None else None,
        available_margin=Decimal(available_margin) if available_margin is not None else None,
        used_margin=Decimal(used_margin) if used_margin is not None else None,
        captured_at=captured_at or datetime.now(UTC),
    )


def make_inputs(
    *,
    account_id: UUID | None = None,
    trading_mode: str = "PAPER",
    positions: tuple | None = None,
    funds: FundsState | None = None,
    prices: dict | None = None,
) -> PortfolioInputs:
    return PortfolioInputs(
        account_id=account_id or uuid4(),
        trading_mode=trading_mode,
        positions=positions or (),
        funds=funds,
        prices=prices or {},
    )


class InMemoryPortfolioRepository:
    """In-memory portfolio snapshot store mirroring durable semantics."""

    def __init__(self) -> None:
        self.snapshots: dict[tuple, PortfolioSnapshot] = {}  # (account, mode, at) -> snapshot
        self.fail_next_save = False

    def _key(self, account_id: UUID, trading_mode: str, snapshot_at: datetime):
        return (account_id, trading_mode.upper(), snapshot_at)

    def save_snapshot(
        self, *, snapshot: PortfolioSnapshot, computation, content_hash: str
    ) -> PortfolioSnapshot:
        if self.fail_next_save:
            self.fail_next_save = False
            raise PortfolioPersistenceError("simulated DB failure")
        key = self._key(snapshot.account_id, snapshot.trading_mode, snapshot.snapshot_at)
        if key in self.snapshots:
            raise DuplicateSnapshotError("duplicate snapshot (unique constraint)")
        persisted = replace(snapshot, snapshot_id=uuid4())
        self.snapshots[key] = persisted
        return persisted

    def load_snapshot(self, *, account_id, trading_mode, snapshot_at):
        return self.snapshots.get(self._key(account_id, trading_mode, snapshot_at))

    def load_latest(self, *, account_id, trading_mode):
        matches = [
            (s.snapshot_at, s)
            for (a, m, _at), s in self.snapshots.items()
            if a == account_id and m == trading_mode.upper()
        ]
        if not matches:
            return None
        return max(matches, key=lambda pair: pair[0])[1]

    def list_snapshots(self, *, account_id, trading_mode, limit=100):
        matches = [
            s for (a, m, _at), s in self.snapshots.items()
            if a == account_id and m == trading_mode.upper()
        ]
        matches.sort(key=lambda s: s.snapshot_at, reverse=True)
        return matches[:limit]
