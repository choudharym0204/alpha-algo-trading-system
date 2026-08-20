"""Angel One SmartAPI adapter (Phase 10).

Auth: ``loginByPassword`` (clientcode + password + TOTP) returns a JWT + refresh
token + feed token; API calls carry ``Authorization: Bearer <jwt>`` and
``X-PrivateKey: <api_key>``. Order execution requires a registered static IP
(modelled as a configuration prerequisite). WebSocket/postbacks provide order
updates; the adapter keeps provider-specific parsing inside the boundary.
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

from angel_one.mapping import (
    ANGEL_BASE_URL,
    ORDER_TYPE_MAP,
    PRODUCT_MAP,
    VALIDITY_MAP,
    build_capabilities,
    map_error,
    map_status,
    variety_for,
)

_SENTINEL = UUID(int=0)


class AngelOneAdapter(BaseBrokerAdapter):
    """Concrete Angel One (SmartAPI) broker adapter."""

    broker_name = BrokerName.ANGEL_ONE

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
            broker=BrokerName.ANGEL_ONE,
            account_reference="",
            credential_reference="",
            api_endpoint=ANGEL_BASE_URL,
            static_ip_required=True,
            static_ip_requirement_note=(
                "Angel One SmartAPI requires a registered static IP for order "
                "execution (effective 2026-04-01)."
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
        self._jwt_token: str | None = None
        self._api_key: str | None = None

    # ------------------------------------------------------------------ auth
    async def authenticate(self, creds: BrokerCredentialsRef) -> BrokerSessionState:
        resolved = self._resolve_credentials(creds.secret_ref)
        self._api_key = resolved.get("api_key") or ""
        client_code = resolved.get("client_code") or creds.account_identifier
        password = resolved.get("password") or ""
        totp = resolved.get("totp") or ""
        if not self._api_key or not client_code or not password:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION,
                "missing Angel One api_key/client_code/password",
            )
        login_resp = await self._transport.request(
            "POST",
            "/rest/auth/angelbroking/user/v1/loginByPassword",
            json={
                "clientcode": client_code,
                "password": password,
                "totp": totp,
            },
        )
        body = login_resp.body or {}
        if body.get("status") is False or login_resp.status_code not in (200, 201):
            raise map_error(login_resp)
        data = body.get("data") or {}
        self._jwt_token = data.get("jwtToken")
        if not self._jwt_token:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION, "login returned no JWT token"
            )
        return BrokerSessionState(
            broker_name=BrokerName.ANGEL_ONE,
            account_identifier=creds.account_identifier,
            connected=True,
            authenticated=True,
            checked_at=datetime.now(UTC),
        )

    async def validate_session(self) -> BrokerSessionState:
        resp = await self._transport.request(
            "GET", "/rest/secure/angelbroking/user/v1/getProfile",
            headers=self._sync_auth_headers(),
        )
        return BrokerSessionState(
            broker_name=BrokerName.ANGEL_ONE,
            account_identifier=self._config.account_reference,
            connected=self.connection_state.value == "CONNECTED",
            authenticated=resp.ok and resp.body.get("status") is not False,
            checked_at=datetime.now(UTC),
        )

    def _sync_auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._jwt_token}",
            "X-PrivateKey": self._api_key or "",
            "Content-Type": "application/json",
        }

    async def _auth_headers(self) -> dict[str, str]:
        return self._sync_auth_headers()

    # --------------------------------------------------------------- transport (do-*)
    _ORDER_V1 = "/rest/secure/angelbroking/order/v1"

    async def _do_submit(self, payload: dict) -> TransportResponse:
        return await self._request(
            "POST", f"{self._ORDER_V1}/placeOrder", json=payload
        )

    async def _do_modify(self, payload: dict, broker_order_id: str) -> TransportResponse:
        body = dict(payload)
        body["orderid"] = broker_order_id
        return await self._request(
            "POST", f"{self._ORDER_V1}/modifyOrder", json=body
        )

    async def _do_cancel(self, broker_order_id: str) -> TransportResponse:
        return await self._request(
            "POST",
            f"{self._ORDER_V1}/cancelOrder",
            json={"orderid": broker_order_id, "variety": "NORMAL"},
        )

    async def _do_get_order(self, broker_order_id: str) -> TransportResponse:
        return await self._request("GET", f"{self._ORDER_V1}/getOrderBook")

    async def _do_get_orders(self) -> TransportResponse:
        return await self._request("GET", f"{self._ORDER_V1}/getOrderBook")

    async def _do_get_trades(self) -> TransportResponse:
        return await self._request("GET", f"{self._ORDER_V1}/getTradeBook")

    async def _do_get_positions(self) -> TransportResponse:
        return await self._request(
            "GET", "/rest/secure/angelbroking/portfolio/v1/getPosition"
        )

    async def _do_get_holdings(self) -> TransportResponse:
        return await self._request(
            "GET", "/rest/secure/angelbroking/portfolio/v1/getHolding"
        )

    async def _do_get_funds(self) -> TransportResponse:
        return await self._request("GET", "/rest/secure/angelbroking/user/v1/getRMS")

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse:
        self._guard_connection()
        resp = await self._do_get_order(broker_order_id)
        if not resp.ok:
            raise self.map_error(resp)
        for order in self.parse_orders_response(resp):
            if order.broker_order_id == broker_order_id:
                return order
        raise BrokerError(
            BrokerErrorClass.NOT_FOUND, f"order {broker_order_id} not found"
        )

    # --------------------------------------------------------------- payloads
    def build_order_payload(self, request: BrokerOrderRequest) -> dict:
        instrument = self._resolve_instrument(request)
        order_type = request.order_type.value
        payload = {
            "variety": variety_for(order_type),
            "tradingsymbol": instrument.symbol,
            "symboltoken": instrument.broker_token or instrument.instrument_key,
            "transactiontype": request.side.value,
            "exchange": request.exchange,
            "ordertype": ORDER_TYPE_MAP[order_type],
            "producttype": PRODUCT_MAP[request.product_type.value],
            "duration": VALIDITY_MAP[request.validity.value],
            "price": str(request.limit_price) if request.limit_price is not None else "0",
            "triggerprice": str(request.stop_price) if request.stop_price is not None else "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(request.quantity),
        }
        return payload

    def build_modify_payload(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> dict:
        payload = self.build_order_payload(request)
        payload["orderid"] = broker_order_id
        return payload

    # --------------------------------------------------------------- parsing
    def parse_order_response(
        self, resp: TransportResponse, request: BrokerOrderRequest | None
    ) -> BrokerOrderResponse:
        body = resp.body or {}
        data = body.get("data") or {}
        order_id = data.get("orderid") if isinstance(data, dict) else None
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
        order_id = data.get("orderid") if isinstance(data, dict) else None
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
            filled = int(row.get("filledquantity") or row.get("filledQuantity") or 0)
            results.append(
                BrokerOrderResponse(
                    status=map_status(
                        row.get("orderstatus") or row.get("status"),
                        filled=filled,
                        quantity=quantity,
                    ),
                    client_order_id=str(row.get("clientorderid") or ""),
                    broker_order_id=str(row.get("orderid")) if row.get("orderid") else None,
                    filled_quantity=Decimal(str(filled)),
                    average_price=_dec(row.get("averageprice")),
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
            net_qty = int(row.get("netqty") or 0)
            if not net_qty:
                continue
            symbol = str(row.get("tradingsymbol") or "")
            snapshots.append(
                BrokerPositionSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for(
                        row.get("exchange") or "", symbol
                    ),
                    trading_mode="PAPER",
                    quantity=Decimal(str(net_qty)),
                    average_price=_dec(row.get("netavgprice")),
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
            symbol = str(row.get("tradingsymbol") or "")
            holdings.append(
                BrokerHoldingSnapshot(
                    broker_account_id=self._broker_account_id,
                    instrument_id=self._instrument_id_for(
                        row.get("exchange") or "", symbol
                    ),
                    quantity=Decimal(str(row.get("quantity") or 0)),
                    average_price=_dec(row.get("averageprice")),
                    exchange=str(row.get("exchange") or ""),
                    symbol=symbol,
                    captured_at=datetime.now(UTC),
                )
            )
        return holdings

    def parse_funds_response(self, resp: TransportResponse) -> BrokerFundsSnapshot:
        body = resp.body or {}
        data = body.get("data") or {}
        return BrokerFundsSnapshot(
            broker_account_id=self._broker_account_id,
            available_margin=_dec(data.get("availablecash")),
            used_margin=_dec(data.get("usedmargin")),
            available_cash=_dec(data.get("availablecash")),
            captured_at=datetime.now(UTC),
        )

    def parse_event(self, raw: dict) -> NormalizedBrokerEvent:
        status = (raw.get("orderstatus") or raw.get("status") or "").lower()
        order_id = raw.get("orderid") or raw.get("order_id")
        filled = int(raw.get("filledquantity") or raw.get("filledQuantity") or 0)
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
            reason=raw.get("statusmessage") or "",
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


__all__ = ["AngelOneAdapter"]
