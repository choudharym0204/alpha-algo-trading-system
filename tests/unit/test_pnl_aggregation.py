"""Phase 13 — aggregation (trade→position→strategy→account, daily) tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from alpha_algo_pnl_engine.aggregation import (
    account_aggregation,
    combine_unrealized,
    daily_aggregation,
    strategy_aggregation,
)
from alpha_algo_pnl_engine.engine import PnlEngine

from pnl_test_support import InMemoryPnlRepository, make_fill, make_position


def make_engine(repo):
    return PnlEngine(repository=repo, global_halt_active=lambda: False)


def _t(ts="2026-08-20T10:00:00+00:00"):
    return datetime.fromisoformat(ts)


def _record(engine, repo, *, account_id, strategy_run_id, instrument_id, side, qty, price, exec_id, t=None):
    position = make_position(
        position_id=uuid4(), account_id=account_id, strategy_run_id=strategy_run_id,
        instrument_id=instrument_id, quantity=100, average_price="100",
    )
    fill = make_fill(
        account_id=account_id, strategy_run_id=strategy_run_id, instrument_id=instrument_id,
        side=side, quantity=qty, price=price, execution_id=exec_id,
        occurred_at=t or _t(),
    )
    return engine.record_fill(fill=fill, position_before=position)


def test_strategy_aggregation_sums_realized():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, s1, s2 = uuid4(), uuid4(), uuid4()

    _record(engine, repo, account_id=acc, strategy_run_id=s1, instrument_id=uuid4(), side="SELL", qty="40", price="120", exec_id="a")  # 800
    _record(engine, repo, account_id=acc, strategy_run_id=s1, instrument_id=uuid4(), side="SELL", qty="50", price="110", exec_id="b")  # 500
    _record(engine, repo, account_id=acc, strategy_run_id=s2, instrument_id=uuid4(), side="SELL", qty="100", price="90", exec_id="c")  # -1000

    events = repo.list_events(account_id=acc)
    strategy = {a.key: a for a in strategy_aggregation(events)}

    assert strategy[str(s1)].realized_gross == Decimal("1300.0000")
    assert strategy[str(s1)].trade_count == 2
    assert strategy[str(s2)].realized_gross == Decimal("-1000.0000")
    assert strategy[str(s2)].trade_count == 1


def test_account_aggregation_equals_sum_of_strategies_no_double_count():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, s1, s2 = uuid4(), uuid4(), uuid4()

    _record(engine, repo, account_id=acc, strategy_run_id=s1, instrument_id=uuid4(), side="SELL", qty="40", price="120", exec_id="a")
    _record(engine, repo, account_id=acc, strategy_run_id=s2, instrument_id=uuid4(), side="SELL", qty="40", price="110", exec_id="b")

    events = repo.list_events(account_id=acc)
    strategies = strategy_aggregation(events)
    accounts = account_aggregation(events)

    assert len(accounts) == 1
    strategy_total = sum((s.realized_gross for s in strategies), Decimal("0"))
    assert accounts[0].realized_gross == strategy_total
    assert accounts[0].trade_count == 2


def test_account_isolation_in_aggregation():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc_a, acc_b = uuid4(), uuid4()

    _record(engine, repo, account_id=acc_a, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", qty="40", price="120", exec_id="a")
    _record(engine, repo, account_id=acc_b, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", qty="40", price="130", exec_id="b")

    accounts = {a.key: a for a in account_aggregation(repo.list_events())}
    assert accounts[str(acc_a)].realized_gross == Decimal("800.0000")
    assert accounts[str(acc_b)].realized_gross == Decimal("1200.0000")
    assert accounts[str(acc_a)].trade_count == 1
    assert accounts[str(acc_b)].trade_count == 1


def test_daily_aggregation_buckets_by_local_day():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc = uuid4()
    tz = timezone(timedelta(hours=5, minutes=30))  # IST

    # 09:30 UTC = 15:00 IST (same day), 20:00 UTC = 01:30 IST (next day)
    _record(engine, repo, account_id=acc, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", qty="40", price="120", exec_id="d1", t=_t("2026-08-20T09:30:00+00:00"))
    _record(engine, repo, account_id=acc, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", qty="40", price="110", exec_id="d2", t=_t("2026-08-20T20:00:00+00:00"))

    daily = {a.key: a for a in daily_aggregation(repo.list_events(account_id=acc), tz=tz)}
    assert "2026-08-20" in daily
    assert "2026-08-21" in daily
    assert daily["2026-08-20"].realized_gross == Decimal("800.0000")
    assert daily["2026-08-21"].realized_gross == Decimal("400.0000")


def test_combine_unrealized_produces_gross_and_net():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc = uuid4()
    _record(engine, repo, account_id=acc, strategy_run_id=uuid4(), instrument_id=uuid4(), side="SELL", qty="40", price="120", exec_id="a")
    accounts = account_aggregation(repo.list_events(account_id=acc))
    combined = combine_unrealized(accounts[0], Decimal("250.0000"))
    assert combined.realized_gross == Decimal("800.0000")
    assert combined.unrealized_pnl == Decimal("250.0000")
    assert combined.gross_pnl == Decimal("1050.0000")
    assert combined.net_pnl == Decimal("1050.0000")
