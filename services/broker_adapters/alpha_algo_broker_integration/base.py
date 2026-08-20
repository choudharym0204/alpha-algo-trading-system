"""Base broker adapter (Phase 10).

Implements the common connection/rate-limit/LIVE-gate plumbing and delegates
provider-specific request/response/status/error mapping to subclasses. Concrete
adapters only supply mapping tables + ``_do_*`` transport calls + parsers.

LIVE safety is enforced here: ``LIVE`` trading mode is always refused, and a
``global_halt_active`` hook (fail-closed default True) blocks all submission.
"""

from __future__ import annotations

import abc
import logging
from datetime import UTC, datetime
from typing import Callable

from alpha_algo_broker_integration.connection import (
    ConnectionStateMachine,
    ReconnectPolicy,
    is_recoverable,
)
from alpha_algo_broker_integration.contracts import (
    BrokerAdapter,
    BrokerCapabilities,
    BrokerConnectionConfig,
    BrokerCredentialsRef,
    BrokerFundsSnapshot,
    BrokerHoldingSnapshot,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerOrderStatus,
    BrokerPositionSnapshot,
    BrokerSessionState,
    ConnectionState,
    TradingMode,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass
from alpha_algo_broker_integration.events import NormalizedBrokerEvent
from alpha_algo_broker_integration.mapping import InstrumentMapping
from alpha_algo_broker_integration.ratelimit import RateLimiter, RateLimitScope
from alpha_algo_broker_integration.transport import (
    BrokerHttpTransport,
    TransportResponse,
)

logger = logging.getLogger(__name__)


class BaseBrokerAdapter(BrokerAdapter, abc.ABC):
    """Shared skeleton for concrete broker adapters."""

    def __init__(
        self,
        *,
        capabilities: BrokerCapabilities,
        config: BrokerConnectionConfig,
        transport: BrokerHttpTransport,
        rate_limiter: RateLimiter | None = None,
        instrument_mapping: InstrumentMapping | None = None,
        global_halt_active: Callable[[], bool] | None = None,
        credential_resolver: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._config = config
        self._transport = transport
        self._rate_limiter = rate_limiter or RateLimiter()
        self._instrument_mapping = instrument_mapping or InstrumentMapping()
        # Fail-closed: halt is active unless a provider says otherwise.
        self._global_halt_active = global_halt_active or (lambda: True)
        self._credential_resolver = credential_resolver
        self._state_machine = ConnectionStateMachine(
            policy=ReconnectPolicy(
                max_attempts=config.retry_policy.max_attempts,
                base_backoff_seconds=config.retry_policy.base_backoff_seconds,
                max_backoff_seconds=config.retry_policy.max_backoff_seconds,
                jitter=config.retry_policy.jitter,
            )
        )
        self._session: BrokerSessionState | None = None
        self._credentials_ref: BrokerCredentialsRef | None = None

    # ------------------------------------------------------------ capabilities
    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._capabilities

    @property
    def connection_state(self) -> ConnectionState:
        return self._state_machine.state

    # ------------------------------------------------------------ safety gates
    def _guard_live(self, trading_mode: TradingMode) -> None:
        if trading_mode == TradingMode.LIVE:
            raise BrokerError(
                BrokerErrorClass.UNSUPPORTED,
                "LIVE trading is disabled (fail-closed)",
            )

    def _guard_halt(self) -> None:
        if self._global_halt_active():
            raise BrokerError(
                BrokerErrorClass.ORDER_REJECTED,
                "global trading halt is active; submission refused",
            )

    def _guard_supported(self, request: BrokerOrderRequest) -> None:
        """Reject unsupported order/product types (never silently downgrade)."""
        from alpha_algo_broker_integration.mapping import require_supported

        require_supported(
            value=request.order_type.value,
            supported=self._capabilities.supported_order_types,
            what="order type",
        )
        require_supported(
            value=request.product_type.value,
            supported=self._capabilities.supported_products,
            what="product type",
        )

    def _guard_connection(self) -> None:
        if self._state_machine.state != ConnectionState.CONNECTED:
            raise BrokerError(
                BrokerErrorClass.NETWORK,
                "broker not connected",
            )

    def _resolve_credentials(self, secret_ref: str) -> dict[str, str]:
        if self._credential_resolver is None:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION,
                "no credential resolver configured",
            )
        return self._credential_resolver(secret_ref)

    def _resolve_instrument(self, request: BrokerOrderRequest):
        """Resolve + validate the broker instrument before submission."""
        return self._instrument_mapping.resolve(
            request.instrument_id,
            exchange=request.exchange,
            symbol=request.symbol,
        )

    # ------------------------------------------------------------ connectivity
    async def connect(self, creds: BrokerCredentialsRef) -> BrokerSessionState:
        self._state_machine.transition(ConnectionState.CONNECTING)
        self._credentials_ref = creds
        try:
            session = await self.authenticate(creds)
            self._session = session
            self._state_machine.transition(ConnectionState.CONNECTED)
            return session
        except BrokerError:
            self._state_machine.transition(ConnectionState.DISCONNECTED)
            raise

    async def disconnect(self) -> None:
        await self.logout()
        self._state_machine.transition(ConnectionState.DISCONNECTED)
        self._session = None

    async def health(self) -> bool:
        return self._state_machine.state == ConnectionState.CONNECTED

    async def reconnect(self) -> BrokerSessionState:
        if self._credentials_ref is None:
            raise BrokerError(
                BrokerErrorClass.AUTHENTICATION, "no credentials to reconnect with"
            )

        async def _connect() -> None:
            session = await self.authenticate(self._credentials_ref)  # type: ignore[arg-type]
            self._session = session

        await self._state_machine.reconnect(connect_fn=_connect)
        return self._session or BrokerSessionState(
            broker_name=self._capabilities.broker_name,
            account_identifier=self._config.account_reference,
            connected=False,
            authenticated=False,
            checked_at=datetime.now(UTC),
            state=self._state_machine.state,
        )

    # ------------------------------------------------------------ auth (abstract)
    @abc.abstractmethod
    async def authenticate(
        self, creds: BrokerCredentialsRef
    ) -> BrokerSessionState: ...

    @abc.abstractmethod
    async def validate_session(self) -> BrokerSessionState: ...

    async def logout(self) -> None:
        self._session = None

    # ------------------------------------------------------------ orders
    async def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        self._guard_live(request.trading_mode)
        self._guard_halt()
        self._guard_supported(request)
        self._guard_connection()
        if not self._capabilities.supports_order_submission:
            raise BrokerError(
                BrokerErrorClass.UNSUPPORTED, "order submission not supported"
            )
        await self._rate_limiter.throttle(RateLimitScope.ORDERS)
        payload = self.build_order_payload(request)
        resp = await self._do_submit(payload)
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_order_response(resp, request)

    async def modify_order(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> BrokerOrderResponse:
        self._guard_live(request.trading_mode)
        self._guard_halt()
        self._guard_supported(request)
        self._guard_connection()
        if not self._capabilities.supports_modify:
            raise BrokerError(BrokerErrorClass.UNSUPPORTED, "modify not supported")
        await self._rate_limiter.throttle(RateLimitScope.ORDERS)
        payload = self.build_modify_payload(request, broker_order_id)
        resp = await self._do_modify(payload, broker_order_id)
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_order_response(resp, request)

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        self._guard_halt()
        self._guard_connection()
        if not self._capabilities.supports_cancel:
            raise BrokerError(BrokerErrorClass.UNSUPPORTED, "cancel not supported")
        await self._rate_limiter.throttle(RateLimitScope.ORDERS)
        resp = await self._do_cancel(broker_order_id)
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_cancel_response(resp, broker_order_id)

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse:
        self._guard_connection()
        resp = await self._do_get_order(broker_order_id)
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_order_response(resp, None)

    async def get_orders(self) -> list[BrokerOrderResponse]:
        self._guard_connection()
        resp = await self._do_get_orders()
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_orders_response(resp)

    async def get_trades(self) -> list[BrokerOrderResponse]:
        self._guard_connection()
        resp = await self._do_get_trades()
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_orders_response(resp)

    # ------------------------------------------------------------ account
    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        self._guard_connection()
        if not self._capabilities.supports_positions:
            raise BrokerError(BrokerErrorClass.UNSUPPORTED, "positions not supported")
        resp = await self._do_get_positions()
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_positions_response(resp)

    async def get_holdings(self) -> list[BrokerHoldingSnapshot]:
        self._guard_connection()
        if not self._capabilities.supports_holdings:
            raise BrokerError(BrokerErrorClass.UNSUPPORTED, "holdings not supported")
        resp = await self._do_get_holdings()
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_holdings_response(resp)

    async def get_funds(self) -> BrokerFundsSnapshot:
        self._guard_connection()
        if not self._capabilities.supports_funds:
            raise BrokerError(BrokerErrorClass.UNSUPPORTED, "funds not supported")
        resp = await self._do_get_funds()
        if not resp.ok:
            raise self.map_error(resp)
        return self.parse_funds_response(resp)

    # ------------------------------------------------------------ events
    @abc.abstractmethod
    def parse_event(self, raw: dict) -> NormalizedBrokerEvent: ...

    # ------------------------------------------------------------ transport hooks
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> TransportResponse:
        headers = await self._auth_headers()
        return await self._transport.request(
            method, path, params=params, json=json, headers=headers
        )

    @abc.abstractmethod
    async def _auth_headers(self) -> dict[str, str]: ...

    # ------------------------------------------------------------ do-* (abstract)
    @abc.abstractmethod
    async def _do_submit(self, payload: dict) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_modify(self, payload: dict, broker_order_id: str) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_cancel(self, broker_order_id: str) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_order(self, broker_order_id: str) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_orders(self) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_trades(self) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_positions(self) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_holdings(self) -> TransportResponse: ...

    @abc.abstractmethod
    async def _do_get_funds(self) -> TransportResponse: ...

    # ------------------------------------------------------------ mapping (abstract)
    @abc.abstractmethod
    def build_order_payload(self, request: BrokerOrderRequest) -> dict: ...

    @abc.abstractmethod
    def build_modify_payload(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> dict: ...

    @abc.abstractmethod
    def parse_order_response(
        self, resp: TransportResponse, request: BrokerOrderRequest | None
    ) -> BrokerOrderResponse: ...

    @abc.abstractmethod
    def parse_cancel_response(
        self, resp: TransportResponse, broker_order_id: str
    ) -> BrokerOrderResponse: ...

    @abc.abstractmethod
    def parse_orders_response(
        self, resp: TransportResponse
    ) -> list[BrokerOrderResponse]: ...

    @abc.abstractmethod
    def parse_positions_response(
        self, resp: TransportResponse
    ) -> list[BrokerPositionSnapshot]: ...

    @abc.abstractmethod
    def parse_holdings_response(
        self, resp: TransportResponse
    ) -> list[BrokerHoldingSnapshot]: ...

    @abc.abstractmethod
    def parse_funds_response(self, resp: TransportResponse) -> BrokerFundsSnapshot: ...

    @abc.abstractmethod
    def map_error(self, resp: TransportResponse) -> BrokerError: ...
