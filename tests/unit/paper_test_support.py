"""Shared helpers for Phase 15 paper-runtime tests (not a test module)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_broker_adapters import BrokerCredentialsRef, TradingMode
from alpha_algo_paper_trading import PaperBrokerAdapter, PaperReferencePrice
from alpha_algo_paper_runtime import (
    PaperAccount,
    PaperAccountStatus,
    PaperCostModel,
    PaperFunds,
    PaperRun,
    PaperRunStatus,
    PaperTradingService,
    compute_config_hash,
    new_paper_run_id,
)

FIXED_NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)


def make_account(
    *,
    account_id: UUID | None = None,
    paper_run_id: UUID | None = None,
    starting_capital: str | Decimal = "100000",
    status: PaperAccountStatus = PaperAccountStatus.ACTIVE,
) -> PaperAccount:
    return PaperAccount(
        account_id=account_id or uuid4(),
        paper_run_id=paper_run_id or new_paper_run_id(),
        trading_mode=TradingMode.PAPER,
        starting_capital=Decimal(starting_capital),
        status=status,
        created_at=FIXED_NOW,
    )


def make_run(
    *,
    paper_run_id: UUID | None = None,
    status: PaperRunStatus = PaperRunStatus.ACTIVE,
    config: dict[str, str] | None = None,
) -> PaperRun:
    return PaperRun(
        paper_run_id=paper_run_id or new_paper_run_id(),
        status=status,
        config_hash=compute_config_hash(config or {"seed": "1"}),
        created_at=FIXED_NOW,
    )


def make_funds(
    *,
    account_id: UUID | None = None,
    available_cash: str | Decimal = "100000",
    reserved_cash: str | Decimal = "0",
) -> PaperFunds:
    return PaperFunds(
        account_id=account_id or uuid4(),
        available_cash=Decimal(available_cash),
        reserved_cash=Decimal(reserved_cash),
    )


def make_reference(
    instrument_id: UUID, last: str = "100", bid: str | None = None, ask: str | None = None
) -> PaperReferencePrice:
    return PaperReferencePrice(
        instrument_id=instrument_id,
        last=Decimal(last),
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        reference_at=FIXED_NOW,
    )


def connect_broker(
    broker: PaperBrokerAdapter, account_id: UUID
) -> PaperBrokerAdapter:
    asyncio.run(
        broker.connect(
            BrokerCredentialsRef(
                broker_name="paper",
                account_identifier=str(account_id),
                secret_ref="__MUST_NOT_BE_READ__",
            )
        )
    )
    return broker


def make_service(
    *,
    account: PaperAccount | None = None,
    broker: PaperBrokerAdapter | None = None,
    reference_prices: dict[UUID, PaperReferencePrice] | None = None,
    cost_model: PaperCostModel | None = None,
    repository=None,
) -> PaperTradingService:
    account = account or make_account()
    broker = broker or PaperBrokerAdapter(
        clock=lambda: FIXED_NOW, reference_prices=reference_prices or {}
    )
    connect_broker(broker, account.account_id)
    return PaperTradingService(
        account=account,
        broker=broker,
        reference_prices=reference_prices,
        cost_model=cost_model,
        clock=lambda: FIXED_NOW,
        repository=repository,
    )


class InMemoryPaperRepository:
    """In-memory paper store mirroring the durable semantics."""

    def __init__(self) -> None:
        self.runs: dict[UUID, PaperRun] = {}
        self.accounts: dict[UUID, PaperAccount] = {}
        self.funds: dict[UUID, PaperFunds] = {}

    def save_run(self, run: PaperRun) -> None:
        self.runs[run.paper_run_id] = run

    def load_run(self, paper_run_id: UUID) -> PaperRun | None:
        return self.runs.get(paper_run_id)

    def save_account(self, account: PaperAccount) -> None:
        self.accounts[account.account_id] = account

    def load_account(self, account_id: UUID) -> PaperAccount | None:
        return self.accounts.get(account_id)

    def save_funds(self, funds: PaperFunds) -> None:
        self.funds[funds.account_id] = funds

    def load_funds(self, account_id: UUID) -> PaperFunds | None:
        return self.funds.get(account_id)
