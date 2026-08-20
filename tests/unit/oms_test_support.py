"""Shared helpers for Phase 8 OMS tests (not a test module).

Provides ``make_intent`` (a fully-populated ``TradingIntent``) and an in-memory
session/store that mirrors the transactional + unique-constraint semantics the
OMS repository relies on (COMMIT = truth, orchestration/identity/client-order
uniqueness backstops, append-only events). This keeps OMS tests honest without a
live PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from alpha_algo_contracts import SignalAction
from alpha_algo_risk_engine.approval import compute_risk_identity_key
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_shared.db.models.safety import OrderEvent
from alpha_algo_shared.db.models.trading import Order
from alpha_algo_signal_engine.identity import compute_signal_identity_key
from alpha_algo_trading_engine.identity import compute_orchestration_identity_key
from alpha_algo_trading_engine.intent import TradingIntent

from signal_test_support import make_signal
from trading_test_support import make_approved_decision


class UniqueViolation(IntegrityError):
    """Mimics a DB unique-constraint violation (concurrency backstop)."""

    def __init__(self, message: str = "unique constraint violation") -> None:
        super().__init__(message, params=None, orig=RuntimeError(message))


def make_intent(
    *,
    action: str = "BUY",
    quantity: str = "10",
    trading_mode: str = "PAPER",
    account_id: UUID | None = None,
    order_type: str = "MARKET",
    orchestration_id: str | None = None,
    limit_price: Decimal | None = None,
    expires_at: datetime | None = None,
    evaluated_at: datetime | None = None,
    strategy_run_id: UUID | None = None,
    signal=None,
) -> TradingIntent:
    signal = signal or make_signal(action=SignalAction(action))
    account = account_id if account_id is not None else uuid4()
    resolved = RiskOrderIntent(
        quantity=Decimal(quantity), account_id=account, order_type=order_type
    )
    binding = compute_risk_identity_key(signal, resolved, trading_mode)
    decision = make_approved_decision(
        signal, binding_hash=binding, expires_at=expires_at, evaluated_at=evaluated_at
    )
    return TradingIntent(
        correlation_id=uuid4(),
        orchestration_id=orchestration_id
        or compute_orchestration_identity_key(signal, resolved, trading_mode),
        account_id=account,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        strategy_config_hash=signal.strategy_config_hash,
        strategy_run_id=strategy_run_id,
        signal_id=signal.signal_id,
        signal_identity_key=compute_signal_identity_key(signal),
        instrument_id=signal.instrument_id,
        action=signal.action.value,
        quantity=Decimal(quantity),
        order_type=order_type,
        limit_price=limit_price,
        trading_mode=trading_mode,
        risk_decision_id=decision.decision_id,
        approval_id=decision.approval_id,
        approval_expires_at=decision.expires_at,
        binding_hash=binding,
        metadata={},
    )


def expired_intent(**overrides) -> TradingIntent:
    now = datetime.now(UTC)
    kwargs = dict(
        evaluated_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(seconds=1),
    )
    kwargs.update(overrides)
    return make_intent(**kwargs)


class InMemoryOmsStore:
    """In-memory orders/events store with unique-constraint backstops."""

    def __init__(self) -> None:
        self.orders: dict[UUID, Order] = {}
        self.events: list[OrderEvent] = []
        self._by_orchestration: dict[str, UUID] = {}
        self._by_identity: dict[str, UUID] = {}
        self._by_client_order_id: dict[str, UUID] = {}
        self._source_event_ids: set[str] = set()
        self._lock = Lock()

    def find_by_id(self, order_id: UUID) -> Order | None:
        return self.orders.get(order_id)

    def find_by_orchestration(self, orchestration_id: str) -> Order | None:
        oid = self._by_orchestration.get(orchestration_id)
        return self.orders.get(oid) if oid else None

    def find_by_client_order_id(self, client_order_id: str) -> Order | None:
        oid = self._by_client_order_id.get(client_order_id)
        return self.orders.get(oid) if oid else None

    def list_orders(self) -> list[Order]:
        return list(self.orders.values())

    def events_for(self, order_id: UUID) -> list[OrderEvent]:
        return [e for e in self.events if e.order_id == order_id]

    def insert_order(self, order: Order) -> None:
        with self._lock:
            if order.orchestration_id in self._by_orchestration:
                raise UniqueViolation("uq_orders_orchestration_id")
            if order.order_identity_key in self._by_identity:
                raise UniqueViolation("uq_orders_order_identity_key")
            if order.client_order_id in self._by_client_order_id:
                raise UniqueViolation("uq_orders_client_order_id")
            self.orders[order.id] = order
            self._by_orchestration[order.orchestration_id] = order.id
            self._by_identity[order.order_identity_key] = order.id
            self._by_client_order_id[order.client_order_id] = order.id

    def insert_event(self, event: OrderEvent) -> None:
        if event.source_event_id and event.source_event_id in self._source_event_ids:
            raise UniqueViolation("uq_order_events_source_event_id")
        self.events.append(event)
        if event.source_event_id:
            self._source_event_ids.add(event.source_event_id)


class OmsSession:
    """Session facade over ``InMemoryOmsStore`` (COMMIT applies staged writes)."""

    def __init__(self, store: InMemoryOmsStore, fail_commit=None) -> None:
        self._store = store
        self._fail_commit = fail_commit
        self._staged: list = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def add(self, obj) -> None:
        self._staged.append(obj)

    def get(self, cls, pk):
        if cls is Order:
            return self._store.find_by_id(pk)
        return None

    def execute(self, stmt):
        return _OmsQueryResult(self._store, stmt)

    def commit(self) -> None:
        if self._fail_commit is not None:
            raise self._fail_commit
        staged, self._staged = self._staged, []
        for obj in staged:
            if isinstance(obj, Order):
                self._store.insert_order(obj)
            elif isinstance(obj, OrderEvent):
                self._store.insert_event(obj)
        self.committed = True

    def rollback(self) -> None:
        self._staged = []
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _OmsQueryResult:
    def __init__(self, store: InMemoryOmsStore, stmt) -> None:
        self._store = store
        self._entity, self._col, self._value, self._is_id = _interpret(stmt)

    def scalar_one_or_none(self):
        if self._entity is not Order:
            return None
        if self._col == "orchestration_id":
            order = self._store.find_by_orchestration(self._value)
            if order is None:
                return None
            return order.id if self._is_id else order
        if self._col == "client_order_id":
            return self._store.find_by_client_order_id(self._value)
        return None

    def scalars(self):
        class _Scalars:
            def __init__(self, items):
                self._items = items

            def all(self):
                return list(self._items)

        if self._entity is Order:
            return _Scalars(self._store.list_orders())
        if self._entity is OrderEvent:
            return _Scalars(self._store.events_for(self._value))
        return _Scalars([])


def _interpret(stmt):
    try:
        froms = list(stmt.get_final_froms())
    except AttributeError:
        froms = list(getattr(stmt, "froms", ()) or ())
    entity = None
    if Order.__table__ in froms:
        entity = Order
    elif OrderEvent.__table__ in froms:
        entity = OrderEvent

    col = None
    value = None
    where = getattr(stmt, "whereclause", None)
    if where is not None and hasattr(where, "left") and hasattr(where.left, "name"):
        col = where.left.name
        right = getattr(where, "right", None)
        value = getattr(right, "value", None)
        if value is None and hasattr(right, "_value"):
            value = right._value

    cols = list(getattr(stmt, "column_descriptions", []) or [])
    is_id = entity is Order and len(cols) == 1 and cols[0].get("name") == "id"
    return entity, col, value, is_id


class OmsSessionFactory:
    """Returns a fresh ``OmsSession`` per call, bound to a shared store.

    ``fail_commit`` makes every session's COMMIT raise (to exercise rollback /
    no-false-success paths). ``fail_commit_once`` raises on the first COMMIT only.
    """

    def __init__(self, store: InMemoryOmsStore | None = None, fail_commit=None) -> None:
        self.store = store or InMemoryOmsStore()
        self.fail_commit = fail_commit
        self.sessions: list[OmsSession] = []
        self._fail_next = False

    def __call__(self) -> OmsSession:
        fail = self.fail_commit
        if self._fail_next:
            fail = RuntimeError("injected commit failure")
            self._fail_next = False
        session = OmsSession(self.store, fail_commit=fail)
        self.sessions.append(session)
        return session

    def fail_next_commit(self) -> None:
        self._fail_next = True
