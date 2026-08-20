"""Phase 10 — concurrency / rate-limit / duplicate-event safety tests."""

import asyncio
from decimal import Decimal

from alpha_algo_broker_integration.events import (
    BrokerEventType,
    EventDeduplicator,
    NormalizedBrokerEvent,
)
from alpha_algo_broker_integration.ratelimit import (
    RateLimiter,
    RateLimitPolicy,
    RateLimitScope,
    TokenBucket,
)


def run(coro):
    return asyncio.run(coro)


def test_token_bucket_enforces_rate():
    bucket = TokenBucket(rate_per_second=2.0, burst=1)
    assert run(bucket.acquire()) is True  # burst token
    assert run(bucket.acquire()) is False  # empty before refill


def test_rate_limiter_no_policy_is_unlimited():
    limiter = RateLimiter()
    assert run(limiter.check(RateLimitScope.ORDERS)) is True


def test_rate_limiter_applies_scope_specific_policy():
    limiter = RateLimiter()
    limiter.add(RateLimitPolicy(RateLimitScope.ORDERS, requests_per_second=1.0, burst=1))
    assert run(limiter.check(RateLimitScope.ORDERS)) is True
    assert run(limiter.check(RateLimitScope.ORDERS)) is False
    # other scopes unaffected
    assert run(limiter.check(RateLimitScope.ACCOUNT)) is True


def test_duplicate_events_produce_single_effect():
    from datetime import UTC, datetime
    from uuid import uuid4

    dedup = EventDeduplicator()
    oid = uuid4()
    fill = NormalizedBrokerEvent(
        order_id=oid,
        event_type=BrokerEventType.FILL,
        broker_order_id="b1",
        fill_quantity=Decimal("10"),
        occurred_at=datetime.now(UTC),
        source_event_id="evt-1",
    )
    applied = 0
    for _ in range(10):  # repeated delivery of the same event
        if dedup.apply(fill):
            applied += 1
    assert applied == 1  # only one effect


def test_distinct_events_are_all_applied():
    from datetime import UTC, datetime
    from uuid import uuid4

    dedup = EventDeduplicator()
    oid = uuid4()
    events = [
        NormalizedBrokerEvent(
            order_id=oid,
            event_type=BrokerEventType.PARTIAL_FILL,
            broker_order_id="b1",
            fill_quantity=Decimal(str(n)),
            occurred_at=datetime.now(UTC),
            source_event_id=f"evt-{i}",
        )
        for i, n in enumerate((3, 4, 3))  # distinct identities
    ]
    applied = sum(1 for e in events if dedup.apply(e))
    assert applied == 3
