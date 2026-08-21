"""In-process domain-event bus (Phase 21).

A minimal, provider-neutral pub/sub for the internal trading event flow. It is
deliberately **not** a distributed broker: there is no Kafka/RabbitMQ/Redis
dependency, no network, and no persistence. Broker/streaming eventing is out of
scope for now ("only if justified" by scale — documented in the review).

Guarantees:

* **Synchronous, deterministic FIFO** dispatch (handlers run in subscription
  order; ``publish_many`` processes events in list order).
* **Handler isolation** — a failing handler is recorded and skipped; it never
  breaks the publisher or other handlers (observability must not break trading).
* **Thread-safe** subscription registry.
* **No-op** variant for unit tests and offline execution.

Secrets can never reach the bus: ``DomainEvent`` already rejects sensitive
payload keys at construction (Phase 21 contract).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from alpha_algo_contracts import DomainEvent

__all__ = [
    "EventBus",
    "HandlerFailure",
    "NoopEventBus",
    "Subscription",
]

WILDCARD = "*"

EventHandler = Callable[[DomainEvent], None]


@dataclass
class HandlerFailure:
    topic: str
    event_id: str
    event_type: str
    error: Exception

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "error": f"{type(self.error).__name__}: {self.error}",
        }


@dataclass
class Subscription:
    topic: str
    handler: EventHandler
    bus: "EventBus"
    _cancelled: bool = False

    def cancel(self) -> None:
        self.bus.unsubscribe(self)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Subscription]] = {}
        self._lock = threading.RLock()
        self._published: int = 0
        self._failures: list[HandlerFailure] = []

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        with self._lock:
            sub = Subscription(topic=topic, handler=handler, bus=self)
            self._handlers.setdefault(topic, []).append(sub)
            return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            subs = self._handlers.get(subscription.topic)
            if subs and subscription in subs:
                subs.remove(subscription)
                subscription._cancelled = True

    def _matching_subs(self, event: DomainEvent) -> list[Subscription]:
        with self._lock:
            exact = list(self._handlers.get(event.event_type, []))
            wildcard = list(self._handlers.get(WILDCARD, []))
        return exact + wildcard

    def publish(self, event: DomainEvent) -> int:
        """Dispatch to matching handlers; return the number invoked (or attempted)."""
        if not isinstance(event, DomainEvent):
            raise TypeError("publish expects a DomainEvent")
        subs = self._matching_subs(event)
        with self._lock:
            self._published += 1
        invoked = 0
        for sub in subs:
            if sub._cancelled:
                continue
            invoked += 1
            try:
                sub.handler(event)
            except Exception as exc:  # isolate handler failure
                with self._lock:
                    self._failures.append(
                        HandlerFailure(
                            topic=sub.topic,
                            event_id=str(event.event_id),
                            event_type=event.event_type,
                            error=exc,
                        )
                    )
        return invoked

    def publish_many(self, events: list[DomainEvent]) -> int:
        total = 0
        for event in events:
            total += self.publish(event)
        return total

    def handler_count(self, topic: str | None = None) -> int:
        with self._lock:
            if topic is None:
                return sum(len(subs) for subs in self._handlers.values())
            return len(self._handlers.get(topic, []))

    def published_count(self) -> int:
        with self._lock:
            return self._published

    def failures(self) -> list[HandlerFailure]:
        with self._lock:
            return list(self._failures)

    def clear_failures(self) -> None:
        with self._lock:
            self._failures.clear()

    def reset(self) -> None:
        with self._lock:
            self._handlers.clear()
            self._published = 0
            self._failures.clear()


class NoopEventBus(EventBus):
    """Accepts subscriptions/publishes but delivers to no one (offline/tests)."""

    def __init__(self) -> None:
        super().__init__()
        self._enabled = False

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        # Return a detached subscription; publish() never invokes handlers.
        return Subscription(topic=topic, handler=handler, bus=self, _cancelled=True)

    def publish(self, event: DomainEvent) -> int:
        if not isinstance(event, DomainEvent):
            raise TypeError("publish expects a DomainEvent")
        return 0

    def handler_count(self, topic: str | None = None) -> int:
        return 0
