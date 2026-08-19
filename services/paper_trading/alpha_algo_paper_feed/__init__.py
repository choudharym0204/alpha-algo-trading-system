"""Paper market-data feed (P8-002).

A PAPER-only bridge that converts caller-supplied, already-validated
``MarketTick`` records into caller-owned ``PaperReferencePrice`` snapshots for
the paper trading simulator (P8-001). Pure, stateless, deterministic: the
feed never fetches, subscribes, streams, embeds sample data, reads the wall
clock, invents quote legs, or touches LIVE/persistence/risk machinery.

``PaperReferencePrice`` is intentionally NOT re-exported here: the type is
owned by ``alpha_algo_paper_trading`` (P8-001) and this package only consumes
it. Source identity is served separately via ``TickProvenance`` /
``provenance_of``.
"""

from __future__ import annotations

from alpha_algo_paper_feed.errors import PaperFeedError
from alpha_algo_paper_feed.mapping import TICK_REFERENCE_POLICY, tick_to_reference
from alpha_algo_paper_feed.provenance import TickProvenance, provenance_of

__all__ = [
    "PaperFeedError",
    "TICK_REFERENCE_POLICY",
    "TickProvenance",
    "provenance_of",
    "tick_to_reference",
]
