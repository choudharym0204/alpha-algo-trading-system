"""Zerodha Kite Connect v3 adapter (Phase 10).

Translates the universal broker contract into Kite Connect REST calls. Auth is
OAuth token-based (``api_key`` + ``access_token``); credentials are resolved via
an injected resolver (never hardcoded / logged). Order execution requires a
registered static IP — modelled as a configuration prerequisite.

Internal <-> broker identity mapping (account, instrument, order id) is resolved
via injected resolvers so provider identifiers never become the core system's
primary identity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_broker_integration.base import BaseBrokerAdapter
from alpha_algo_broker_integration.contracts import (
    BrokerConnectionConfig,
    BrokerCredentialsRef,
    BrokerFundsSnapshot,
    BrokerHoldingSnapshot,
    BrokerName,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerOrderStatus,
    BrokerPositionSnapshot,
    BrokerSessionState,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass
from alpha_algo_broker_integration.events import (
    BrokerEventType,
    NormalizedBrokerEvent,
)
from alpha_algo_broker_integration.transport import TransportResponse

from zerodha.mapping import (
    KITE_BASE_URL,
    ORDER_TYPE_MAP,
    PRODUCT_MAP,
    VALIDITY_MAP,
    build_capabilities,
    map_error,
    map_status,
)

_SENTINEL = UUID(int=0)


class ZerodhaAdapter(BaseBrokerAdapter):
    """Concrete Zerodha (Kite Connect v3) broker adapter."""

    broker_name = BrokerName.ZERODHA

    def __init__(
        self,
        transport,
        *,
        broker_account_id: UUID | None = None,
        order_id_resolver=None,
        **kwargs,
    ) -> None:
        capabilities = build_capabilities()
        config = BrokerConnectionConfig(
            broker=BrokerName.ZERODHA,
            account_reference="",
            credential_reference="",
            api_endpoint=KITE_BASE_URL,
            static_ip_required=True,
            static_ip_requirement_note=(
                "Kite Connect requires a registered static IP for order placement "
                "(effective 2025-04-01)."
            ),
        )
        super().__init__(
            capabilities=capabilities,
            config=config,
            transport=transport,
            **kwargs,
        )
        self._broker_account_id = broker_account_id or _SENTINEL
        self._order_id_resolver = order_id_resolver
        self._api_key: str | None = None
        self._access_token: str | None = None

    # ------------------------------------------------------------------ auth
    async def authenticate(self, creds: BrokerCredentialsRef) -> BrokerSessionState:
        resolved = self._resolve_credentials(creds.secret_ref)
        self._api_key = resolved.get("api_key") or ""
        self._access_token = resolved.get("access_token") or ""
        if not self._api_key or not self._access_token:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION,
                "missing Zerodha api_key/access_token",
            )
        resp = await self._transport.request(
            "GET", "/user/profile", headers=self._sync_auth_headers()
        )
        if resp.status_code == 401:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION,
                "invalid Zerodha access token",
                provider_code="401",
            )
        if not resp.ok:
            raise map_error(resp)
        return BrokerSessionState(
            broker_name=BrokerName.ZERODHA,
            account_identifier=creds.account_identifier,
            connected=True,
            authenticated=True,
            checked_at=datetime.now(UTC),
        )

    async def validate_session(self) -> BrokerSessionState:
        resp = await self._transport.request(
            "GET", "/user/profile", headers=self._sync_auth_headers()
        )
        return BrokerSessionState(
            broker_name=BrokerName.ZERODHA,
            account_identifier=self._config.account_reference,
            connected=self.connection_state.value == "CONNECTED",
            authenticated=resp.ok and resp.status_code != 401,
            checked_at=datetime.now(UTC),
        )

    def _sync_auth_headers(self) -> dict[str, str]:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

    async def _auth_headers(self) -> dict[str, str]:
        return self._sync_auth_headers()

    # ----------------------------------------------------------- transport (do-*)
    async def _do_submit(self, payload: dict) -> TransportResponse:
        return await self._request("POST", "/orders", json=payload)

    async def _do_modify(self, payload: dict, broker_order_id: str) -> TransportResponse:
        return await self._request("PUT", f"/orders/{broker_order_id}", json=payload)

    async def _do_cancel(self, broker_order_id: str) -> TransportResponse:
        return await self._request("DELETE", f"/orders/{broker_order_id}")

    async def _do_get_order(self, broker_order_id: str) -> TransportResponse:
        return await self._request("GET", f"/orders/{broker_order_id}")

    async def _do_get_orders(self) -> TransportResponse:
        return await self._request("GET", "/orders")

    async def _do_get_trades(self) -> TransportResponse:
        return await self._request("GET", "/trades")

    async def _do_get_positions(self) -> TransportResponse:
        return await self._request("GET", "/portfolio/positions")

    async def _do_get_holdings(self) -> TransportResponse:
        return await self._request("GET", "/portfolio/holdings")

    async def _do_get_funds(self) -> TransportResponse:
        return await self._request("GET", "/user/margins")

    # --------------------------------------------------------------- payloads
    def build_order_payload(self, request: BrokerOrderRequest) -> dict:
        instrument = self._resolve_instrument(request)
        payload = {
            "exchange": request.exchange,
            "tradingsymbol": instrument.symbol,
            "transaction_type": request.side.value,
            "quantity": request.quantity,
            "product": PRODUCT_MAP[request.product_type.value],
            "order_type": ORDER_TYPE_MAP[request.order_type.value],
            "validity": VALIDITY_MAP[request.validity.value],
            "tag": request.client_order_id,
        }
        if request.limit_price is not None:
            payload["price"] = float(request.limit_price)
        if request.stop_price is not None:
            payload["trigger_price"] = float(request.stop_price)
        return payload

    def build_modify_payload(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> dict:
        return self.build_order_payload(request)

    # --------------------------------------------------------------- parsing
    def parse_order_response(
        self, resp: TransportResponse, request: BrokerOrderRequest | None
    ) -> BrokerOrderResponse:
        body = resp.body or {}
        data = body.get("data") or {}
        order_id = data.get("order_id") if isinstance(data, dict) else None
        return BrokerOrderResponse(
            status=BrokerOrderStatus.BROKER_ACKNOWLEDGED,
            client_order_id=(request.client_order_id if request else ""),
            broker_order_id=str(order_id) if order_id else None,
            message=body.get("message"),
            timestamp=datetime.now(UTC),
            raw_reference=str(order_id) if order_id else None,
        )

    def parse_cancel_response(
        self, resp: TransportResponse, broker_order_id: str
    ) -> BrokerOrderResponse:
        body = resp.body or {}
        data = body.get("data") or {}
        order_id = data.get("order_id") if isinstance(data, dict) else None
        return BrokerOrderResponse(
            status=BrokerOrderStatus.CANCELLED,
            client_order_id="",
            broker_order_id=str(order_id) if order_id else broker_order_id,
            message=body.get("message"),
            timestamp=datetime.now(UTC),
            raw_reference=str(order_id) if order_id else None,
        )

    def parse_orders_response(
        self, resp: TransportResponse
    ) -> list[BrokerOrderResponse]:
        body = resp.body or {}
        rows = body.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        results: list[BrokerOrderResponse] = []
        for row in rows:
            quantity = int(row.get("quantity") or 0)
            filled = int(row.get("filled_quantity") or 0)
            results.append(
                BrokerOrderResponse(
                    status=map_status(
                        row.get("status"), filled=filled, quantity=quantity
                    ),
                    client_order_id=str(row.get("tag") or ""),
                    broker_order_id=str(row.get("order_id")) if row.get("order_id") else None,
                    filled_quantity=Decimal(str(filled)),
                    average_price=_dec(row.get("average_price")),
                    timestamp=datetime.now(UTC),
                )
            )
        return results

    def parse_positions_response(
        self, resp: TransportResponse
    ) -> list[BrokerPositionSnapshot]:
        body = resp.body or {}
        data = body.get("data") or {}
        if isinstance(data, dict):
            net = data.get("net") or []
        else:
            net = []
        snapshots: list[BrokerPositionSnapshot] = []
        for row in net:
            if not row.get("quantity"):
                continue
            snapshots.append(
                BrokerPositionSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for(
                        row.get("exchange") or "", row.get("tradingsymbol") or ""
                    ),
                    trading_mode="PAPER",
                    quantity=Decimal(str(row.get("quantity") or 0)),
                    average_price=_dec(row.get("average_price")),
                    exchange=row.get("exchange") or "",
                    symbol=row.get("tradingsymbol") or "",
                    captured_at=datetime.now(UTC),
                )
            )
        return snapshots

    def parse_holdings_response(
        self, resp: TransportResponse
    ) -> list[BrokerHoldingSnapshot]:
        body = resp.body or {}
        rows = body.get("data") or []
        holdings: list[BrokerHoldingSnapshot] = []
        for row in rows:
            holdings.append(
                BrokerHoldingSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for(
                        row.get("exchange") or "", row.get("tradingsymbol") or ""
                    ),
                    quantity=Decimal(str(row.get("quantity") or 0)),
                    average_price=_dec(row.get("average_price")),
                    exchange=row.get("exchange") or "",
                    symbol=row.get("tradingsymbol") or "",
                    captured_at=datetime.now(UTC),
                )
            )
        return holdings

    def parse_funds_response(self, resp: TransportResponse) -> BrokerFundsSnapshot:
        body = resp.body or {}
        data = body.get("data") or {}
        equity = data.get("equity") or {}
        available = equity.get("available") or {}
        return BrokerFundsSnapshot(
            broker_account_id=self._broker_account_id,
            available_cash=_dec(available.get("cash")),
            available_margin=_dec(available.get("adhoc_margin")),
            captured_at=datetime.now(UTC),
        )

    def parse_event(self, raw: dict) -> NormalizedBrokerEvent:
        status = raw.get("status")
        order_id = raw.get("order_id")
        filled = int(raw.get("filled_quantity") or 0)
        quantity = int(raw.get("quantity") or 0)
        if status == "COMPLETE" or (quantity and filled >= quantity):
            event_type = BrokerEventType.FILL
        elif filled > 0:
            event_type = BrokerEventType.PARTIAL_FILL
        elif status == "REJECTED":
            event_type = BrokerEventType.REJECTED
        elif status == "CANCELLED":
            event_type = BrokerEventType.CANCELLED
        else:
            event_type = BrokerEventType.ORDER_UPDATE
        return NormalizedBrokerEvent(
            order_id=self._order_id_for(str(order_id)) if order_id else _SENTINEL,
            event_type=event_type,
            broker_order_id=str(order_id) if order_id else None,
            fill_quantity=Decimal(str(filled)),
            occurred_at=datetime.now(UTC),
            reason=raw.get("status_message") or "",
            source_event_id=str(order_id) if order_id else None,
        )

    def map_error(self, resp: TransportResponse) -> BrokerError:
        return map_error(resp)

    # --------------------------------------------------------------- identity
    def _instrument_id_for(self, exchange: str, symbol: str) -> UUID:
        mapped = self._instrument_mapping.find_by_symbol(exchange=exchange, symbol=symbol)
        return mapped.internal_instrument_id if mapped else _SENTINEL

    def _order_id_for(self, broker_order_id: str) -> UUID:
        if self._order_id_resolver is None:
            return _SENTINEL
        resolved = self._order_id_resolver(broker_order_id)
        return resolved if resolved is not None else _SENTINEL


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


__all__ = ["ZerodhaAdapter"]
