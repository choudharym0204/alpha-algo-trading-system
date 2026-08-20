from __future__ import annotations

"""PAPER-mode-only broker adapter implementing the BrokerAdapter Protocol.

Fills are simulator-confirmed: they exist only as explicit
:class:`~alpha_algo_execution_engine.BrokerOrderEvent`\\ s derived from
injected reference prices, never as ``submit_order`` return values, and never
from live/broker/market-data sources. Paper results are simulated and are
labeled PAPER everywhere (ADR-0007).

Least privilege: the constructor takes an injected clock and a caller-owned
reference-price snapshot — no credentials, no environment, no network clients,
no file paths, no database sessions. ``connect`` never reads ``secret_ref`` and
reports ``authenticated=False`` because a paper session performs no
authentication.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from alpha_algo_broker_adapters import (
    BrokerAdapter,
    BrokerCapabilities,
    BrokerCredentialsRef,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPositionSnapshot,
    BrokerQuote,
    BrokerSessionState,
    TradingMode,
)
from alpha_algo_execution_engine import BrokerOrderEvent

from alpha_algo_paper_trading.book import PaperOrderBook
from alpha_algo_paper_trading.errors import (
    PaperAdapterError,
    PaperMarketDataUnavailableError,
)
from alpha_algo_paper_trading.types import PaperReferencePrice, now_from

__all__ = ["PaperBrokerAdapter"]


class PaperBrokerAdapter(BrokerAdapter):
    """Deterministic paper-mode simulator implementing the BrokerAdapter
    Protocol (P3-001).

    - ``capabilities.supports_live_trading`` is ``False`` (P3-001 marker).
    - ``capabilities.supports_order_cancel`` is ``False``: v1 has no working
      orders (every order reaches a terminal state at submission), so
      cancellation is unsupported and fails loud.
    - ``get_quote`` raises: reference prices are injected, never fetched.
    - ``submit_order`` never returns a fill; fills are exposed as
      ``BrokerOrderEvent``\\ s via ``pending_events`` / ``events_for``.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        reference_prices: Mapping[UUID, PaperReferencePrice],
    ) -> None:
        if not callable(clock):
            raise PaperAdapterError("clock must be callable")
        self._clock = clock
        self._book = PaperOrderBook(clock=clock)
        self._reference_prices = dict(reference_prices)
        self._connected = False
        self._account_identifier: str | None = None
        # client_order_id -> broker_account_id, so events_for can resolve the
        # account-scoped book key (S5/M3).
        self._account_by_client: dict[str, UUID] = {}

    @property
    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker_name="paper",
            supports_market_data=False,
            supports_order_submission=True,
            supports_order_cancel=False,  # v1: no working orders (honest)
            supports_positions=True,
            supports_live_trading=False,
        )

    async def connect(self, credentials_ref: BrokerCredentialsRef) -> BrokerSessionState:
        """Open a paper session.

        Validates the broker name and account identifier but deliberately never
        reads ``credentials_ref.secret_ref``: paper sessions hold and verify no
        credentials, so the returned session reports ``authenticated=False``.
        """
        if credentials_ref.broker_name != "paper":
            raise PaperAdapterError(
                f"paper broker accepts only broker_name='paper', got "
                f"{credentials_ref.broker_name!r}"
            )
        if not credentials_ref.account_identifier.strip():
            raise PaperAdapterError("account_identifier is required")
        # secret_ref is intentionally never read.
        self._connected = True
        self._account_identifier = credentials_ref.account_identifier
        return BrokerSessionState(
            broker_name="paper",
            account_identifier=credentials_ref.account_identifier,
            connected=True,
            authenticated=False,  # paper sessions perform no authentication
            checked_at=now_from(self._clock),
            expires_at=None,
        )

    async def disconnect(self) -> None:
        """Close the paper session. No resources were acquired, so this only
        clears the connected flag — it does not fake tearing anything down."""
        self._connected = False

    def set_reference_price(
        self, instrument_id: UUID, reference: PaperReferencePrice
    ) -> None:
        """Replace the injected reference for one instrument (simulated market step).

        Enables a deterministic, time-ordered market sequence for replay; never
        fetches market data.
        """
        self._reference_prices[instrument_id] = reference

    async def get_quote(self, instrument_id: UUID) -> BrokerQuote:
        """Market data is not supported by the paper broker.

        Present for Protocol conformance only; always raises. Reference prices
        are injected at construction, never fetched (rules 2/11/12).
        """
        raise PaperMarketDataUnavailableError(
            "market data is not supported by the paper broker; reference "
            "prices are injected, never fetched"
        )

    async def submit_order(
        self, request: BrokerOrderRequest
    ) -> BrokerOrderResponse:
        """Submit one PAPER order to the simulator.

        Never returns a fill: the response is ACCEPTED or REJECTED only, and
        any fill is exposed as explicit ``BrokerOrderEvent``\\ s (rule 11 —
        fills are simulator-confirmed, never assumed). Requires
        ``metadata["order_id"]`` to equal the deterministic paper order id
        derived from the broker account and client order id.
        """
        if not self._connected:
            raise PaperAdapterError("paper broker is not connected")
        reference = self._reference_prices.get(request.instrument_id)
        response = self._book.submit(request, reference=reference)
        self._account_by_client[request.client_order_id] = request.broker_account_id
        return response

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancellation is unsupported in the v1 paper simulator.

        v1 has no working orders (every order reaches a terminal state at
        submission), so there is nothing to cancel. Fails loud rather than
        returning a fake CANCELLED outcome (rule 1).
        """
        raise PaperAdapterError(
            "paper v1 simulator has no working orders; cancellation unsupported"
        )

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        """Return PAPER-labeled position snapshots derived from
        simulator-confirmed fills.

        Note: in v1 the connected ``account_identifier`` is session metadata
        only — snapshots are returned for every account that has fills in the
        book. Binding the connected account to ``broker_account_id`` UUIDs is
        a later operational concern (S5/L6). Flat (zero-net) positions are not
        reported (S5/L1).
        """
        if not self._connected:
            raise PaperAdapterError("paper broker is not connected")
        snapshots: list[BrokerPositionSnapshot] = []
        account_ids = {fill.broker_account_id for fill in self._book.fill_records()}
        for account_id in sorted(account_ids, key=str):
            for position in self._book.positions(account_id):
                snapshots.append(
                    BrokerPositionSnapshot(
                        broker_account_id=position.broker_account_id,
                        instrument_id=position.instrument_id,
                        trading_mode=TradingMode.PAPER,
                        quantity=position.quantity,
                        average_price=position.average_price,
                        captured_at=position.captured_at,
                        raw_payload={
                            "fill_source": "paper_simulator",
                            # M2 convention: quantity-weighted mean of ALL fills
                            # (buys and sells), NOT average-cost basis of the
                            # remaining net position.
                            "average_price_convention": "mean_fill_price",
                        },
                    )
                )
        return snapshots

    def pending_events(self) -> tuple[BrokerOrderEvent, ...]:
        """Return unconsumed simulator events (engine drain point).

        The engine applies each event exactly once through
        ``OrderExecutionState.apply_event`` in FIFO order; replay for
        reconciliation is available via ``events_for``.
        """
        return self._book.pending_events()

    def events_for(self, client_order_id: str) -> tuple[BrokerOrderEvent, ...]:
        """Full immutable event history for one client order id (replay)."""
        broker_account_id = self._account_by_client.get(client_order_id)
        if broker_account_id is None:
            return ()
        return self._book.events_for(broker_account_id, client_order_id)
