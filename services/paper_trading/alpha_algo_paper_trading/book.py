from __future__ import annotations

"""In-memory, append-only, idempotent paper order book (foundation).

The book is the single source of truth for paper submissions. It records every
request/response/event pair, derives deterministic order ids from the broker
account and client order id, and aggregates PAPER-labeled positions from the
immutable fill trail. It performs no I/O, no persistence, and no wall-clock
reads: all timestamps come from the injected clock (ADR-0007).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

from alpha_algo_broker_adapters import (
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerOrderStatus,
    OrderSide,
    TradingMode,
)
from alpha_algo_execution_engine import BrokerOrderEvent, OrderEventType

from alpha_algo_paper_trading.errors import (
    ClientOrderIdConflictError,
    PaperAdapterError,
    PaperModeViolationError,
    UnsupportedOrderTypeError,
)
from alpha_algo_paper_trading.fill_policy import decide_fill
from alpha_algo_paper_trading.types import (
    AVERAGE_PRICE_QUANTUM,
    AVERAGE_PRICE_ROUNDING,
    PaperFillRecord,
    PaperPosition,
    PaperReferencePrice,
    now_from,
)

#: Fixed UUIDv5 namespace for deterministic paper order ids.
ORDER_ID_NAMESPACE = UUID("8f4e1a2b-3c4d-4e5f-8a9b-0c1d2e3f4a5b")

__all__ = [
    "ORDER_ID_NAMESPACE",
    "PaperOrderBook",
    "paper_order_id",
]


def paper_order_id(broker_account_id: UUID, client_order_id: str) -> UUID:
    """Deterministic bridge from ``client_order_id`` to the event ``order_id``.

    ``BrokerOrderRequest`` carries only a string ``client_order_id``, while
    ``BrokerOrderEvent.order_id`` must match the execution-engine lifecycle
    UUID. This function derives that UUID deterministically, so idempotency is
    structural: the same account + client order id always maps to the same
    order id (ADR-0007).
    """
    return uuid5(ORDER_ID_NAMESPACE, f"{broker_account_id}:{client_order_id}")


@dataclass(frozen=True)
class SubmissionRecord:
    """Immutable record of one paper submission (idempotency cache entry)."""

    request: BrokerOrderRequest
    response: BrokerOrderResponse
    events: tuple[BrokerOrderEvent, ...]


# Fields that define the trading payload of a request. Two submissions with the
# same client_order_id must match on all of these or the duplicate is a
# conflict, not a retry.
_PAYLOAD_FIELDS = (
    "broker_account_id",
    "instrument_id",
    "trading_mode",
    "side",
    "order_type",
    "quantity",
    "risk_approval_id",
    "limit_price",
    "stop_price",
)


class PaperOrderBook:
    """Append-only paper order book with ``client_order_id`` idempotency.

    Constructor takes only the injected clock — no credentials, no environment,
    no network clients, no file paths, no database sessions (least privilege).
    """

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        if not callable(clock):
            raise PaperAdapterError("clock must be callable")
        self._clock = clock
        # Idempotency cache keyed by (broker_account_id, client_order_id): the
        # deterministic order id is namespaced per account, so the same client
        # order id may legitimately be reused across accounts (S5/M3).
        self._submissions: dict[tuple[UUID, str], SubmissionRecord] = {}
        self._events: list[BrokerOrderEvent] = []
        self._fills: list[PaperFillRecord] = []
        self._pending_index = 0
        self._sequence = 0

    # -- submission ---------------------------------------------------------

    def submit(
        self,
        request: BrokerOrderRequest,
        *,
        reference: PaperReferencePrice | None,
    ) -> BrokerOrderResponse:
        """Submit one PAPER order.

        Raises ``PaperModeViolationError`` for any non-PAPER mode (identity
        check), ``PaperAdapterError`` when ``metadata["order_id"]`` is missing
        or does not match the deterministic paper order id, and
        ``ClientOrderIdConflictError`` when a client order id is reused (for
        the same account) with a different payload. A duplicate with an
        identical payload returns the recorded response and enqueues no new
        events. The order-id contract is enforced on EVERY submission,
        including idempotent retries (S5/M1): a retry with a tampered or
        missing metadata order id fails loud instead of silently returning the
        cached response.
        """
        if request.trading_mode is not TradingMode.PAPER:
            raise PaperModeViolationError(
                f"paper book accepts only TradingMode.PAPER orders, got {request.trading_mode}"
            )
        if not request.client_order_id.strip():
            raise PaperAdapterError("client_order_id is required")
        if request.quantity <= 0:
            raise PaperAdapterError("quantity must be positive")

        order_id = self._resolve_order_id(request)
        key = (request.broker_account_id, request.client_order_id)
        recorded = self._submissions.get(key)
        if recorded is not None:
            self._assert_identical_payload(recorded.request, request)
            return recorded.response

        now = now_from(self._clock)

        if reference is None:
            return self._reject(
                request, order_id, now, "no reference price available for instrument"
            )
        if reference.instrument_id != request.instrument_id:
            raise PaperAdapterError(
                "injected reference price does not match request instrument"
            )

        try:
            decision = decide_fill(request, reference)
        except UnsupportedOrderTypeError as exc:
            # Unsupported order types are a fill-policy outcome, not caller
            # misuse: the broker surface converts them into a REJECTED
            # response plus a REJECTED event so the execution engine can land
            # the order in a terminal state.
            return self._reject(request, order_id, now, str(exc))

        if not decision.fills:
            return self._reject(request, order_id, now, decision.reason or "order not executable")

        return self._accept_and_fill(request, order_id, now, decision.fill_price)

    # -- event / fill exposure ----------------------------------------------

    def pending_events(self) -> tuple[BrokerOrderEvent, ...]:
        """Return unconsumed events in sequence order and clear the drain
        buffer (engine-facing drain semantics)."""
        unconsumed = tuple(self._events[self._pending_index :])
        self._pending_index = len(self._events)
        return unconsumed

    def events(self) -> tuple[BrokerOrderEvent, ...]:
        """Full append-only event log (non-destructive; for reconciliation)."""
        return tuple(self._events)

    def events_for(
        self, broker_account_id: UUID, client_order_id: str
    ) -> tuple[BrokerOrderEvent, ...]:
        """Replay the full event history for one (account, client order id)."""
        recorded = self._submissions.get((broker_account_id, client_order_id))
        return recorded.events if recorded is not None else ()

    def fill_records(self) -> tuple[PaperFillRecord, ...]:
        """Immutable fill trail, sorted by sequence."""
        return tuple(self._fills)

    def positions(self, broker_account_id: UUID) -> tuple[PaperPosition, ...]:
        """Aggregate PAPER positions for one account from the fill trail.

        Net quantity is the signed sum of fills (BUY positive, SELL negative).
        Average price is the quantity-weighted mean of all fills for the
        instrument, quantized to ``AVERAGE_PRICE_QUANTUM`` with
        ``AVERAGE_PRICE_ROUNDING``; it is ``None`` when total quantity is zero.
        """
        grouped: dict[UUID, list[PaperFillRecord]] = {}
        for fill in self._fills:
            if fill.broker_account_id == broker_account_id:
                grouped.setdefault(fill.instrument_id, []).append(fill)

        positions: list[PaperPosition] = []
        captured_at = now_from(self._clock)  # single read per call (S5/L7)
        for instrument_id in sorted(grouped):
            fills = grouped[instrument_id]
            total_quantity = sum((fill.fill_quantity for fill in fills), Decimal("0"))
            signed_quantity = sum(
                (
                    fill.fill_quantity
                    if fill.side is OrderSide.BUY
                    else -fill.fill_quantity
                )
                for fill in fills
            )
            if signed_quantity == Decimal("0"):
                # Flat positions (full round trips) are not reported (S5/L1).
                continue
            total_cost = sum(
                (fill.fill_price * fill.fill_quantity for fill in fills),
                Decimal("0"),
            )
            if total_quantity > Decimal("0"):
                average_price = (
                    total_cost / total_quantity
                ).quantize(AVERAGE_PRICE_QUANTUM, rounding=AVERAGE_PRICE_ROUNDING)
            else:
                average_price = None
            positions.append(
                PaperPosition(
                    broker_account_id=broker_account_id,
                    instrument_id=instrument_id,
                    trading_mode=TradingMode.PAPER,
                    quantity=signed_quantity,
                    average_price=average_price,
                    captured_at=captured_at,
                )
            )
        return tuple(positions)

    # -- internals ----------------------------------------------------------

    def _resolve_order_id(self, request: BrokerOrderRequest) -> UUID:
        expected = paper_order_id(request.broker_account_id, request.client_order_id)
        raw = request.metadata.get("order_id")
        if raw is None:
            raise PaperAdapterError(
                "metadata['order_id'] is required (must equal the deterministic paper order id)"
            )
        try:
            provided = UUID(str(raw))
        except (ValueError, TypeError):
            raise PaperAdapterError(
                "metadata['order_id'] must be a valid UUID string"
            ) from None
        if provided != expected:
            raise PaperAdapterError(
                f"metadata['order_id'] {provided} does not match deterministic "
                f"paper order id {expected}"
            )
        return expected

    def _assert_identical_payload(
        self, prior: BrokerOrderRequest, request: BrokerOrderRequest
    ) -> None:
        for field_name in _PAYLOAD_FIELDS:
            if getattr(prior, field_name) != getattr(request, field_name):
                raise ClientOrderIdConflictError(
                    f"client_order_id {request.client_order_id!r} reused with a "
                    f"different payload ({field_name} differs)"
                )

    def _reject(
        self,
        request: BrokerOrderRequest,
        order_id: UUID,
        now: datetime,
        reason: str,
    ) -> BrokerOrderResponse:
        event = BrokerOrderEvent(
            order_id=order_id,
            event_type=OrderEventType.REJECTED,
            occurred_at=now,
            reason=reason,
            broker_order_id=None,
            fill_quantity=Decimal("0"),
            metadata={
                "trading_mode": "PAPER",
                "client_order_id": request.client_order_id,
                "fill_source": "paper_simulator",
            },
        )
        response = BrokerOrderResponse(
            status=BrokerOrderStatus.REJECTED,
            client_order_id=request.client_order_id,
            broker_order_id=None,
            accepted_at=now,
            reason=reason,
            raw_payload={"source": "paper_simulator"},
        )
        self._record(request, response, (event,))
        return response

    def _accept_and_fill(
        self,
        request: BrokerOrderRequest,
        order_id: UUID,
        now: datetime,
        fill_price: Decimal,
    ) -> BrokerOrderResponse:
        broker_order_id = f"paper-{order_id.hex}"
        ack = BrokerOrderEvent(
            order_id=order_id,
            event_type=OrderEventType.BROKER_ACKNOWLEDGED,
            occurred_at=now,
            reason="paper broker accepted order",
            broker_order_id=broker_order_id,
            fill_quantity=Decimal("0"),
            metadata={
                "trading_mode": "PAPER",
                "client_order_id": request.client_order_id,
                "fill_source": "paper_simulator",
            },
        )
        fill = BrokerOrderEvent(
            order_id=order_id,
            event_type=OrderEventType.FILL,
            occurred_at=now,
            reason="paper simulator-confirmed fill",
            broker_order_id=broker_order_id,
            fill_quantity=Decimal(request.quantity),
            metadata={
                "trading_mode": "PAPER",
                "client_order_id": request.client_order_id,
                "fill_source": "paper_simulator",
                "paper_fill_price": str(fill_price),
            },
        )
        fill_record = PaperFillRecord(
            sequence=self._sequence,
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            order_id=order_id,
            side=request.side,
            instrument_id=request.instrument_id,
            broker_account_id=request.broker_account_id,
            fill_quantity=Decimal(request.quantity),
            fill_price=fill_price,
            occurred_at=now,
        )
        self._sequence += 1
        self._fills.append(fill_record)

        response = BrokerOrderResponse(
            status=BrokerOrderStatus.ACCEPTED,
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            accepted_at=now,
            reason=None,
            raw_payload={"source": "paper_simulator"},
        )
        self._record(request, response, (ack, fill))
        return response

    def _record(
        self,
        request: BrokerOrderRequest,
        response: BrokerOrderResponse,
        events: tuple[BrokerOrderEvent, ...],
    ) -> None:
        key = (request.broker_account_id, request.client_order_id)
        self._submissions[key] = SubmissionRecord(
            request=request, response=response, events=events
        )
        self._events.extend(events)
