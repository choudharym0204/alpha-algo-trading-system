from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class OrderState(StrEnum):
    INTENT_CREATED = "INTENT_CREATED"
    INTERNAL_ORDER_CREATED = "INTERNAL_ORDER_CREATED"
    SUBMISSION_REQUESTED = "SUBMISSION_REQUESTED"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


TERMINAL_ORDER_STATES = frozenset(
    {
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    }
)


ALLOWED_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.INTENT_CREATED: frozenset({OrderState.INTERNAL_ORDER_CREATED}),
    OrderState.INTERNAL_ORDER_CREATED: frozenset(
        {OrderState.SUBMISSION_REQUESTED, OrderState.REJECTED}
    ),
    OrderState.SUBMISSION_REQUESTED: frozenset(
        {
            OrderState.BROKER_ACKNOWLEDGED,
            OrderState.REJECTED,
            OrderState.UNKNOWN,
            OrderState.CANCEL_REQUESTED,
        }
    ),
    OrderState.BROKER_ACKNOWLEDGED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCEL_REQUESTED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.CANCEL_REQUESTED: frozenset(
        {
            OrderState.CANCELLED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.UNKNOWN: frozenset({OrderState.RECONCILIATION_REQUIRED}),
    OrderState.RECONCILIATION_REQUIRED: frozenset(
        {
            OrderState.BROKER_ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
        }
    ),
    OrderState.FILLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.CANCELLED: frozenset(),
}


class InvalidOrderTransition(ValueError):
    pass


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class OrderStateTransition:
    from_state: OrderState
    to_state: OrderState
    occurred_at: datetime
    reason: str
    event_id: UUID = field(default_factory=uuid4)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_timezone(self.occurred_at, "occurred_at")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class OrderLifecycle:
    order_id: UUID
    state: OrderState = OrderState.INTENT_CREATED
    transitions: tuple[OrderStateTransition, ...] = ()

    def transition_to(
        self,
        to_state: OrderState,
        *,
        occurred_at: datetime,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> OrderLifecycle:
        if to_state not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidOrderTransition(
                f"cannot transition order {self.order_id} from {self.state} to {to_state}"
            )

        transition = OrderStateTransition(
            from_state=self.state,
            to_state=to_state,
            occurred_at=occurred_at,
            reason=reason,
            metadata=metadata or {},
        )
        return OrderLifecycle(
            order_id=self.order_id,
            state=to_state,
            transitions=(*self.transitions, transition),
        )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_ORDER_STATES

    @property
    def requires_reconciliation(self) -> bool:
        return self.state in {OrderState.UNKNOWN, OrderState.RECONCILIATION_REQUIRED}
