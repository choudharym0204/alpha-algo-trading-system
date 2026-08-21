"""Alpha Algo internal event architecture (Phase 21).

A unified domain-event envelope (see ``alpha_algo_contracts.events``) and an
in-process event bus (``bus.py``) for the internal trading event flow. This is
an additive decoupling layer for cross-cutting subscribers (observability,
audit, notification); it does not rewire the tested synchronous pipeline and
introduces no distributed broker.
"""

from __future__ import annotations

from .bus import EventBus, EventHandler, HandlerFailure, NoopEventBus, Subscription

__all__ = [
    "EventBus",
    "EventHandler",
    "HandlerFailure",
    "NoopEventBus",
    "Subscription",
]

__version__ = "0.1.0"
