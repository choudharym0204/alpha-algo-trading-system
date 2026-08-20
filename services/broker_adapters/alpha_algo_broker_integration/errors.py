"""Universal broker error model (Phase 10).

Every adapter maps provider-specific errors into ``BrokerError`` with a
normalized ``BrokerErrorClass``, preserving the provider code/message and a
safe retry classification. No raw credential or sensitive provider response
data is ever placed in these errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BrokerErrorClass(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    RATE_LIMIT = "RATE_LIMIT"
    VALIDATION = "VALIDATION"
    ORDER_REJECTED = "ORDER_REJECTED"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED = "UNSUPPORTED"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


# Classes that are *safe to retry* without risk of duplicating an order.
_RETRYABLE = frozenset(
    {
        BrokerErrorClass.RATE_LIMIT,
        BrokerErrorClass.TIMEOUT,
        BrokerErrorClass.NETWORK,
        BrokerErrorClass.PROVIDER_UNAVAILABLE,
    }
)


@dataclass(frozen=True)
class BrokerError(Exception):
    """Normalized broker error (safe, non-leaky)."""

    error_class: BrokerErrorClass
    message: str
    provider_code: str | None = None
    provider_message: str | None = None
    correlation_id: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        # ``retryable`` defaults from the class when not explicitly provided.
        if not self.retryable:
            object.__setattr__(self, "retryable", self.error_class in _RETRYABLE)
        super().__init__(self.message)


def is_safe_to_retry(error_class: BrokerErrorClass) -> bool:
    return error_class in _RETRYABLE


def unknown_broker_error(message: str, **kwargs) -> BrokerError:
    return BrokerError(error_class=BrokerErrorClass.UNKNOWN, message=message, **kwargs)
