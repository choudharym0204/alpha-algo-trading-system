"""Shared helpers for Phase 14 reconciliation tests (not a test module)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from threading import Lock
from uuid import UUID, uuid4

from alpha_algo_reconciliation_engine.contracts import (
    Discrepancy,
    ExecutionObservation,
    FundsObservation,
    OrderObservation,
    PositionObservation,
    ReconciliationRun,
)
from alpha_algo_reconciliation_engine.errors import DuplicateDiscrepancyError, ReconciliationPersistenceError


def make_order_obs(
    *,
    source="internal",
    broker_order_id=None,
    client_order_id=None,
    account_id=None,
    instrument_id=None,
    side="BUY",
    quantity=100,
    order_type="MARKET",
    status="FILLED",
    observed_at=None,
) -> OrderObservation:
    return OrderObservation(
        source=source, broker_order_id=broker_order_id, client_order_id=client_order_id,
        account_id=account_id, instrument_id=instrument_id, side=side, quantity=quantity,
        order_type=order_type, status=status, observed_at=observed_at,
    )


def make_exec_obs(
    *,
    source="internal",
    broker_execution_id=None,
    execution_id=None,
    order_id=None,
    broker_order_id=None,
    account_id=None,
    instrument_id=None,
    side="BUY",
    quantity="100",
    price="100",
    fees="0",
    status="FILLED",
    observed_at=None,
) -> ExecutionObservation:
    return ExecutionObservation(
        source=source, broker_execution_id=broker_execution_id, execution_id=execution_id,
        order_id=order_id, broker_order_id=broker_order_id, account_id=account_id,
        instrument_id=instrument_id, side=side, quantity=Decimal(quantity), price=Decimal(price),
        fees=Decimal(fees), status=status, observed_at=observed_at,
    )


def make_position_obs(
    *,
    source="internal",
    account_id=None,
    instrument_id=None,
    quantity=100,
    side="LONG",
    average_price="100",
    observed_at=None,
) -> PositionObservation:
    return PositionObservation(
        source=source, account_id=account_id, instrument_id=instrument_id, quantity=quantity,
        side=side, average_price=Decimal(average_price) if average_price is not None else None, observed_at=observed_at,
    )


def make_funds_obs(
    *,
    source="internal",
    account_id=None,
    available_cash="1000000",
    available_margin="800000",
    used_margin="200000",
    currency="INR",
    observed_at=None,
) -> FundsObservation:
    return FundsObservation(
        source=source, account_id=account_id,
        available_cash=Decimal(available_cash) if available_cash is not None else None,
        available_margin=Decimal(available_margin) if available_margin is not None else None,
        used_margin=Decimal(used_margin) if used_margin is not None else None,
        currency=currency, observed_at=observed_at,
    )


class InMemoryReconciliationRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, ReconciliationRun] = {}
        self.discrepancies: dict[str, Discrepancy] = {}
        self.fail_next_run = False
        self.fail_next_discrepancy = False
        self._lock = Lock()

    def save_run(self, *, run: ReconciliationRun) -> ReconciliationRun:
        if self.fail_next_run:
            self.fail_next_run = False
            raise ReconciliationPersistenceError("simulated run write failure")
        with self._lock:
            persisted = replace(run, run_id=run.run_id or uuid4())
            self.runs[persisted.run_id] = persisted
            return persisted

    def load_run(self, run_id: UUID) -> ReconciliationRun | None:
        return self.runs.get(run_id)

    def save_discrepancy(self, *, discrepancy: Discrepancy) -> Discrepancy:
        if self.fail_next_discrepancy:
            self.fail_next_discrepancy = False
            raise ReconciliationPersistenceError("simulated discrepancy write failure")
        with self._lock:
            if discrepancy.discrepancy_key in self.discrepancies:
                raise DuplicateDiscrepancyError(discrepancy.discrepancy_key)
            persisted = replace(discrepancy, id=uuid4())
            self.discrepancies[discrepancy.discrepancy_key] = persisted
            return persisted

    def load_discrepancy(self, discrepancy_key: str) -> Discrepancy | None:
        return self.discrepancies.get(discrepancy_key)

    def list_discrepancies(self, *, run_id=None, account_id=None) -> list[Discrepancy]:
        out = []
        for d in self.discrepancies.values():
            if run_id is not None and d.run_id != run_id:
                continue
            if account_id is not None and d.account_id != account_id:
                continue
            out.append(d)
        return out
