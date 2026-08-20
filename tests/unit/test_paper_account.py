from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_broker_adapters import TradingMode
from alpha_algo_paper_runtime import PaperAccount, PaperAccountStatus

from paper_test_support import make_account


def test_account_defaults_are_paper_and_active() -> None:
    acct = make_account()
    assert acct.trading_mode is TradingMode.PAPER
    assert acct.status is PaperAccountStatus.ACTIVE
    assert acct.is_active is True


def test_account_requires_paper_mode() -> None:
    with pytest.raises(ValueError, match="PAPER"):
        PaperAccount(
            account_id=uuid4(),
            paper_run_id=uuid4(),
            trading_mode=TradingMode.LIVE,
            starting_capital=Decimal("100000"),
            status=PaperAccountStatus.ACTIVE,
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
        )


def test_account_requires_positive_starting_capital() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_account(starting_capital="0")


def test_account_rejects_negative_starting_capital() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_account(starting_capital="-100")


def test_account_rejects_naive_created_at() -> None:
    acct = make_account()
    with pytest.raises(ValueError, match="timezone-aware"):
        PaperAccount(
            account_id=acct.account_id,
            paper_run_id=acct.paper_run_id,
            trading_mode=TradingMode.PAPER,
            starting_capital=Decimal("100000"),
            status=PaperAccountStatus.ACTIVE,
            created_at=datetime(2026, 3, 1),  # naive
        )


def test_account_suspended_is_not_active() -> None:
    acct = make_account(status=PaperAccountStatus.SUSPENDED)
    assert acct.is_active is False
