"""Persistence: write validated canonical market data into TimescaleDB models.

PostgreSQL/TimescaleDB is the authoritative market-data history store; Redis is
not used as a source of truth. The repository receives a ``session_factory`` so
it stays decoupled from any specific app wiring.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_shared.db.models import Candle, Tick

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
T = TypeVar("T")


def to_orm_tick(tick: MarketTick) -> Tick:
    """Map a canonical ``MarketTick`` to the ``Tick`` ORM model."""
    return Tick(
        timestamp=tick.timestamp,
        instrument_id=tick.instrument_id,
        exchange=tick.exchange,
        symbol=tick.symbol,
        ltp=tick.ltp,
        volume=tick.volume,
        bid=tick.bid,
        ask=tick.ask,
        bid_quantity=tick.bid_quantity,
        ask_quantity=tick.ask_quantity,
        source_broker=tick.source_broker,
        source_sequence=tick.source_sequence,
        received_at=tick.received_at,
    )


def to_orm_candle(candle: MarketCandle) -> Candle:
    """Map a canonical ``MarketCandle`` to the ``Candle`` ORM model."""
    return Candle(
        candle_start=candle.candle_start,
        instrument_id=candle.instrument_id,
        timeframe=candle.timeframe.value,
        open_price=candle.open_price,
        high_price=candle.high_price,
        low_price=candle.low_price,
        close_price=candle.close_price,
        volume=candle.volume,
        source_broker=candle.source_broker,
        generated_at=candle.generated_at,
    )


class MarketDataRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def _commit_one(self, orm_object: T) -> None:
        session = self._session_factory()
        try:
            session.add(orm_object)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def persist_tick(self, tick: MarketTick) -> None:
        self._commit_one(to_orm_tick(tick))

    def persist_candle(self, candle: MarketCandle) -> None:
        self._commit_one(to_orm_candle(candle))

    def persist_tick_batch(self, ticks: list[MarketTick]) -> None:
        session = self._session_factory()
        try:
            for tick in ticks:
                session.add(to_orm_tick(tick))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def persist_candle_batch(self, candles: list[MarketCandle]) -> None:
        session = self._session_factory()
        try:
            for candle in candles:
                session.add(to_orm_candle(candle))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
