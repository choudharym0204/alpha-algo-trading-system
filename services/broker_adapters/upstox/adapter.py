"""Upstox API v2 adapter (Phase 10).

OAuth2 bearer-token auth; order placement via ``/order/place`` using an
``instrument_token`` resolved through the instrument-mapping layer. Sandbox
endpoints are supported and selected by configuration. WebSocket (V3) is the
order-update mechanism (not polling).
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

from upstox.mapping import (
    ORDER_TYPE_MAP,
    PRODUCT_MAP,
    UPSTOX_BASE_URL,
    VALIDITY_MAP,
    build_capabilities,
    map_error,
    map_status,
)

_SENTINEL = UUID(int=0)


class UpstoxAdapter(BaseBrokerAdapter):
    """Concrete Upstox (API v2) broker adapter."""

    broker_name = BrokerName.UPSTOX

    def __init__(
        self,
        transport,
        *,
        broker_account_id: UUID | None = None,
        order_id_resolver=None,
        environment: str = "PAPER",
        **kwargs,
    ) -> None:
        capabilities = build_capabilities()
        config = BrokerConnectionConfig(
            broker=BrokerName.UPSTOX,
            account_reference="",
            credential_reference="",
            environment=environment,
            api_endpoint=UPSTOX_BASE_URL,
            static_ip_required=False,
        )
        super().__init__(
            capabilities=capabilities,
            config=config,
            transport=transport,
            **kwargs,
        )
        self._broker_account_id = broker_account_id or _SENTINEL
        self._order_id_resolver = order_id_resolver
        self._access_token: str | None = None

    # ------------------------------------------------------------------ auth
    async def authenticate(self, creds: BrokerCredentialsRef) -> BrokerSessionState:
        resolved = self._resolve_credentials(creds.secret_ref)
        self._access_token = resolved.get("access_token") or ""
        if not self._access_token:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION, "missing Upstox access_token"
            )
        resp = await self._transport.request(
            "GET", "/user/profile", headers=self._sync_auth_headers()
        )
        if resp.status_code in (401, 403):
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION,
                "invalid Upstox access token",
                provider_code=str(resp.status_code),
            )
        if not resp.ok:
            raise map_error(resp)
        return BrokerSessionState(
            broker_name=BrokerName.UPSTOX,
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
            broker_name=BrokerName.UPSTOX,
            account_identifier=self._config.account_reference,
            connected=self.connection_state.value == "CONNECTED",
            authenticated=resp.ok and resp.status_code not in (401, 403),
            checked_at=datetime.now(UTC),
        )

    def _sync_auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    async def _auth_headers(self) -> dict[str, str]:
        return self._sync_auth_headers()

    # --------------------------------------------------------------- transport (do-*)
    async def _do_submit(self, payload: dict) -> TransportResponse:
        return await self._request("POST", "/order/place", json=payload)

    async def _do_modify(self, payload: dict, broker_order_id: str) -> TransportResponse:
        body = dict(payload)
        body["order_id"] = broker_order_id
        return await self._request("PUT", "/order/modify", json=body)

    async def _do_cancel(self, broker_order_id: str) -> TransportResponse:
        return await self._request(
            "DELETE", "/order/cancel", json={"order_id": broker_order_id}
        )

    async def _do_get_order(self, broker_order_id: str) -> TransportResponse:
        return await self._request(
            "GET", "/order/history", params={"order_id": broker_order_id}
        )

    async def _do_get_orders(self) -> TransportResponse:
        return await self._request("GET", "/order/retrieve-all")

    async def _do_get_trades(self) -> TransportResponse:
        return await self._request("GET", "/order/trades/get-trades-for-day")

    async def _do_get_positions(self) -> TransportResponse:
        return await self._request("GET", "/portfolio/short-term-positions")

    async def _do_get_holdings(self) -> TransportResponse:
        return await self._request("GET", "/portfolio/long-term-holdings")

    async def _do_get_funds(self) -> TransportResponse:
        return await self._request("GET", "/user/get-funds-and-margin")

    # --------------------------------------------------------------- payloads
    def build_order_payload(self, request: BrokerOrderRequest) -> dict:
        instrument = self._resolve_instrument(request)
        payload = {
            "quantity": request.quantity,
            "product": PRODUCT_MAP[request.product_type.value],
            "validity": VALIDITY_MAP[request.validity.value],
            "price": float(request.limit_price) if request.limit_price is not None else 0.0,
            "tag": request.client_order_id,
            "instrument_token": instrument.broker_token or instrument.instrument_key,
            "order_type": ORDER_TYPE_MAP[request.order_type.value],
            "transaction_type": request.side.value,
            "disclosed_quantity": 0,
            "trigger_price": float(request.stop_price) if request.stop_price is not None else 0.0,
            "is_amo": False,
        }
        return payload

    def build_modify_payload(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> dict:
        payload = self.build_order_payload(request)
        payload["order_id"] = broker_order_id
        return payload

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
            message=body.get("message") if isinstance(body, dict) else None,
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
            message=body.get("message") if isinstance(body, dict) else None,
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
        rows = body.get("data") or []
        snapshots: list[BrokerPositionSnapshot] = []
        for row in rows:
            if not row.get("quantity"):
                continue
            symbol = str(row.get("tradingsymbol") or row.get("instrument_token") or "")
            snapshots.append(
                BrokerPositionSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for("", symbol),
                    trading_mode="PAPER",
                    quantity=Decimal(str(row.get("quantity") or 0)),
                    average_price=_dec(row.get("average_price")),
                    exchange=str(row.get("exchange") or ""),
                    symbol=symbol,
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
            symbol = str(row.get("tradingsymbol") or row.get("instrument_token") or "")
            holdings.append(
                BrokerHoldingSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for("", symbol),
                    quantity=Decimal(str(row.get("quantity") or 0)),
                    average_price=_dec(row.get("average_price")),
                    exchange=str(row.get("exchange") or ""),
                    symbol=symbol,
                    captured_at=datetime.now(UTC),
                )
            )
        return holdings

    def parse_funds_response(self, resp: TransportResponse) -> BrokerFundsSnapshot:
        body = resp.body or {}
        data = body.get("data") or {}
        equity = data.get("equity") or {}
        return BrokerFundsSnapshot(
            broker_account_id=self._broker_account_id,
            available_margin=_dec(equity.get("available_margin")),
            used_margin=_dec(equity.get("used_margin")),
            available_cash=_dec(equity.get("available_cash")),
            captured_at=datetime.now(UTC),
        )

    def parse_event(self, raw: dict) -> NormalizedBrokerEvent:
        status = (raw.get("status") or "").lower()
        order_id = raw.get("order_id")
        filled = int(raw.get("filled_quantity") or 0)
        quantity = int(raw.get("quantity") or 0)
        if status == "complete" or (quantity and filled >= quantity):
            event_type = BrokerEventType.FILL
        elif filled > 0:
            event_type = BrokerEventType.PARTIAL_FILL
        elif status == "rejected":
            event_type = BrokerEventType.REJECTED
        elif status == "cancelled":
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
        if mapped is not None:
            return mapped.internal_instrument_id
        # Fall back to a token-only match (Upstox uses instrument_token).
        for instrument in self._instrument_mapping._by_id.values():  # type: ignore[attr-defined]
            if instrument.broker_token == symbol or instrument.instrument_key == symbol:
                return instrument.internal_instrument_id
        return _SENTINEL

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


__all__ = ["UpstoxAdapter"]
