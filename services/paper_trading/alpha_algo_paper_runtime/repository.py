from __future__ import annotations

"""Paper persistence boundary (Phase 15).

``PaperRepository`` is the durable store for paper-specific state (runs,
accounts, funds). Paper orders/executions/positions already persist through the
Phase 8/9/11 repositories and are deliberately **not** duplicated here.

The in-memory double lives in tests; ``SqlPaperRepository`` maps the ORM models
(``alpha_algo_shared.db.models.paper``) to the runtime types. No credential
values and no live-broker state ever pass through this boundary.
"""

from typing import Callable, Protocol
from uuid import UUID

from alpha_algo_paper_runtime.account import PaperAccount
from alpha_algo_paper_runtime.funds import PaperFunds
from alpha_algo_paper_runtime.run import PaperRun


class PaperRepository(Protocol):
    def save_run(self, run: PaperRun) -> None: ...

    def load_run(self, paper_run_id: UUID) -> PaperRun | None: ...

    def save_account(self, account: PaperAccount) -> None: ...

    def load_account(self, account_id: UUID) -> PaperAccount | None: ...

    def save_funds(self, funds: PaperFunds) -> None: ...

    def load_funds(self, account_id: UUID) -> PaperFunds | None: ...


class SqlPaperRepository:
    """PostgreSQL-backed paper repository (SQLAlchemy).

    ``session_factory`` returns a scoped session. Each method opens a short
    transaction; funds are upserted by the unique ``account_id`` constraint.
    """

    def __init__(self, session_factory: Callable) -> None:
        self._session_factory = session_factory

    def save_run(self, run: PaperRun) -> None:
        from alpha_algo_shared.db.models.paper import PaperRun as PaperRunRow

        with self._session_factory() as session:
            row = PaperRunRow(
                id=run.paper_run_id,
                config_hash=run.config_hash,
                status=run.status.value,
                started_at=run.created_at,
                completed_at=run.completed_at,
            )
            session.add(row)
            session.commit()

    def load_run(self, paper_run_id: UUID) -> PaperRun | None:
        from alpha_algo_shared.db.models.paper import PaperRun as PaperRunRow
        from alpha_algo_paper_runtime.run import PaperRunStatus

        with self._session_factory() as session:
            row = session.get(PaperRunRow, paper_run_id)
            if row is None:
                return None
            return PaperRun(
                paper_run_id=row.id,
                config_hash=row.config_hash,
                status=PaperRunStatus(row.status),
                created_at=row.started_at,
                completed_at=row.completed_at,
            )

    def save_account(self, account: PaperAccount) -> None:
        from alpha_algo_shared.db.models.paper import PaperAccount as PaperAccountRow

        with self._session_factory() as session:
            row = PaperAccountRow(
                id=account.account_id,
                paper_run_id=account.paper_run_id,
                trading_mode=account.trading_mode.value,
                starting_capital=account.starting_capital,
                status=account.status.value,
                reset_at=account.reset_at,
            )
            session.add(row)
            session.commit()

    def load_account(self, account_id: UUID) -> PaperAccount | None:
        from alpha_algo_broker_adapters import TradingMode
        from alpha_algo_shared.db.models.paper import PaperAccount as PaperAccountRow
        from alpha_algo_paper_runtime.account import PaperAccountStatus

        with self._session_factory() as session:
            row = session.get(PaperAccountRow, account_id)
            if row is None:
                return None
            return PaperAccount(
                account_id=row.id,
                paper_run_id=row.paper_run_id,
                trading_mode=TradingMode(row.trading_mode),
                starting_capital=row.starting_capital,
                status=PaperAccountStatus(row.status),
                created_at=row.created_at,
                reset_at=row.reset_at,
            )

    def save_funds(self, funds: PaperFunds) -> None:
        from sqlalchemy import select
        from alpha_algo_shared.db.models.paper import PaperFunds as PaperFundsRow

        with self._session_factory() as session:
            existing = session.execute(
                select(PaperFundsRow).where(PaperFundsRow.account_id == funds.account_id)
            ).scalar_one_or_none()
            if existing is not None:
                existing.available_cash = funds.available_cash
                existing.reserved_cash = funds.reserved_cash
                existing.currency = funds.currency
            else:
                session.add(
                    PaperFundsRow(
                        account_id=funds.account_id,
                        available_cash=funds.available_cash,
                        reserved_cash=funds.reserved_cash,
                        currency=funds.currency,
                    )
                )
            session.commit()

    def load_funds(self, account_id: UUID) -> PaperFunds | None:
        from sqlalchemy import select
        from alpha_algo_shared.db.models.paper import PaperFunds as PaperFundsRow

        with self._session_factory() as session:
            row = session.execute(
                select(PaperFundsRow).where(PaperFundsRow.account_id == account_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return PaperFunds(
                account_id=row.account_id,
                available_cash=row.available_cash,
                reserved_cash=row.reserved_cash,
                currency=row.currency,
            )
