"""Normalization: provider payload → canonical ``MarketTick`` / ``MarketCandle``.

Coercion helpers tolerate the string/number forms providers typically emit and
let pydantic enforce the canonical contract (price > 0, timezone-aware
timestamps, OHLC range). The existing contracts are reused unchanged.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick
from alpha_algo_market_data.provider import EventKind, RawMarketEvent
from alpha_algo_market_data.validation import RawEventValidationError


def _coerce_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise RawEventValidationError(f"{field} is not a valid datetime") from exc
    raise RawEventValidationError(f"{field} must be a datetime")


def _coerce_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise RawEventValidationError(f"{field} is not a valid number") from exc
    if not result.is_finite():
        raise RawEventValidationError(f"{field} must be a finite number")
    return result


def _coerce_optional_decimal(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    return _coerce_decimal(value, field)


def _coerce_uuid(value: Any, field: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as exc:
            raise RawEventValidationError(f"{field} is not a valid UUID") from exc
    raise RawEventValidationError(f"{field} must be a UUID")


def normalize_tick(event: RawMarketEvent) -> MarketTick:
    """Convert a raw tick event into a canonical ``MarketTick``."""
    payload = event.payload
    try:
        return MarketTick(
            instrument_id=_coerce_uuid(payload["instrument_id"], "instrument_id"),
            exchange=payload["exchange"],
            symbol=payload["symbol"],
            timestamp=_coerce_datetime(payload["timestamp"], "timestamp"),
            ltp=_coerce_decimal(payload["ltp"], "ltp"),
            volume=payload.get("volume"),
            bid=_coerce_optional_decimal(payload.get("bid"), "bid"),
            ask=_coerce_optional_decimal(payload.get("ask"), "ask"),
            bid_quantity=payload.get("bid_quantity"),
            ask_quantity=payload.get("ask_quantity"),
            source_broker=payload["source_broker"],
            source_sequence=payload["source_sequence"],
            received_at=event.received_at,
        )
    except ValidationError as exc:
        raise RawEventValidationError(str(exc)) from exc


def normalize_candle(event: RawMarketEvent) -> MarketCandle:
    """Convert a raw candle event into a canonical ``MarketCandle``."""
    payload = event.payload
    try:
        timeframe = payload["timeframe"]
        if not isinstance(timeframe, CandleTimeframe):
            try:
                timeframe = CandleTimeframe(timeframe)
            except ValueError as exc:
                raise RawEventValidationError(
                    f"timeframe is not valid: {timeframe!r}"
                ) from exc
        return MarketCandle(
            instrument_id=_coerce_uuid(payload["instrument_id"], "instrument_id"),
            exchange=payload["exchange"],
            symbol=payload["symbol"],
            timeframe=timeframe,
            candle_start=_coerce_datetime(payload["candle_start"], "candle_start"),
            open_price=_coerce_decimal(payload["open_price"], "open_price"),
            high_price=_coerce_decimal(payload["high_price"], "high_price"),
            low_price=_coerce_decimal(payload["low_price"], "low_price"),
            close_price=_coerce_decimal(payload["close_price"], "close_price"),
            volume=payload.get("volume"),
            source_broker=payload["source_broker"],
            generated_at=_coerce_datetime(payload.get("generated_at"), "generated_at"),
        )
    except ValidationError as exc:
        raise RawEventValidationError(str(exc)) from exc


def normalize(event: RawMarketEvent) -> MarketTick | MarketCandle:
    if event.kind == EventKind.TICK:
        return normalize_tick(event)
    return normalize_candle(event)
