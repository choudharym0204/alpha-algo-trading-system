from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_paper_runtime import PaperFunds

from paper_test_support import make_funds


def test_reserve_moves_available_to_reserved() -> None:
    f = make_funds(available_cash="1000").reserve(Decimal("300"))
    assert f.available_cash == Decimal("700")
    assert f.reserved_cash == Decimal("300")


def test_release_moves_reserved_back_to_available() -> None:
    f = make_funds(available_cash="1000").reserve(Decimal("300")).release(Decimal("300"))
    assert f.available_cash == Decimal("1000")
    assert f.reserved_cash == Decimal("0")


def test_reserve_insufficient_funds_raises() -> None:
    with pytest.raises(ValueError, match="insufficient"):
        make_funds(available_cash="100").reserve(Decimal("200"))


def test_release_exceeding_reserved_raises() -> None:
    with pytest.raises(ValueError, match="reserved"):
        make_funds(available_cash="100").release(Decimal("1"))


def test_settle_buy_consumes_reserved_only() -> None:
    f = make_funds(available_cash="1000").reserve(Decimal("300")).settle_buy(Decimal("300"))
    assert f.available_cash == Decimal("700")  # cash already left at reserve
    assert f.reserved_cash == Decimal("0")  # reservation consumed


def test_settle_buy_exceeding_reserved_raises() -> None:
    with pytest.raises(ValueError, match="reserved"):
        make_funds(available_cash="1000").settle_buy(Decimal("1"))


def test_credit_sell_increases_available() -> None:
    f = make_funds(available_cash="1000").credit_sell(Decimal("1100"))
    assert f.available_cash == Decimal("2100")


def test_available_cash_never_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        PaperFunds(account_id=uuid4(), available_cash=Decimal("-1"))


def test_total_cash_is_sum() -> None:
    f = make_funds(available_cash="1000").reserve(Decimal("200"))
    assert f.total_cash == Decimal("1000")
