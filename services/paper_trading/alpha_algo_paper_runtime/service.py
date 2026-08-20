from __future__ import annotations

"""Paper Trading Service (Phase 15) — the operational paper runtime.

Orchestrates one paper account + run: validates orders, submits through the
PAPER-only broker, applies a deterministic cost model (slippage + commission),
and maintains the cash/reserve funds ledger. It never touches LIVE, never calls
a real broker, never computes P&L (Phase 13 owns that), and never mutates
positions directly (fills flow through the broker -> execution events boundary).

Funds validation is a **service-level pre-submission guard**: the v1 paper
broker is funds-unaware by design (ADR-0007), so insufficient-funds and inactive
account rejections are returned as REJECTED outcomes before any broker fill.
Broker-level rejections (no reference price, unsupported order type,
non-executable limit) still flow through the broker and emit normalized events.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Mapping
from uuid import UUID

from alpha_algo_broker_adapters import (
    BrokerOrderRequest,
    BrokerPositionSnapshot,
    OrderSide,
    OrderType,
    TradingMode,
)
from alpha_algo_execution_engine import OrderEventType

from alpha_algo_paper_runtime.account import PaperAccount, PaperAccountStatus
from alpha_algo_paper_runtime.costs import (
    PaperCostModel,
    apply_slippage,
    commission_amount,
)
from alpha_algo_paper_runtime.funds import PaperFunds
from alpha_algo_paper_runtime.repository import PaperRepository
from alpha_algo_paper_trading.book import paper_order_id
from alpha_algo_paper_trading.errors import PaperAdapterError
from alpha_algo_paper_trading.fill_policy import decide_fill
from alpha_algo_paper_trading.paper_broker import PaperBrokerAdapter
from alpha_algo_paper_trading.types import PaperReferencePrice

__all__ = ["PaperFillOutcome", "PaperTradingService"]


@dataclass(frozen=True)
class PaperFillOutcome:
    """Normalized, immutable result of one paper order attempt."""

    client_order_id: str
    order_id: UUID
    side: OrderSide
    instrument_id: UUID
    quantity: int
    fill_price: Decimal | None       # broker raw fill price (None when rejected)
    effective_price: Decimal | None  # after slippage (None when rejected)
    commission: Decimal
    net_cash: Decimal               # signed: BUY negative, SELL positive
    accepted: bool
    reason: str | None
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.tzinfo.utcoffset(self.occurred_at) is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.accepted:
            if self.fill_price is None or self.fill_price <= Decimal("0"):
                raise ValueError("accepted outcome requires a positive fill_price")
            if self.effective_price is None or self.effective_price <= Decimal("0"):
                raise ValueError("accepted outcome requires a positive effective_price")


class PaperTradingService:
    """Operational PAPER runtime for one account + run.

    The constructor takes the same caller-owned ``reference_prices`` mapping the
    paper broker uses, so funds pre-flight and broker fill decisions agree on the
    same deterministic inputs (ADR-0007).
    """

    def __init__(
        self,
        *,
        account: PaperAccount,
        broker: PaperBrokerAdapter,
        reference_prices: Mapping[UUID, PaperReferencePrice] | None = None,
        cost_model: PaperCostModel | None = None,
        clock: Callable[[], datetime],
        repository: PaperRepository | None = None,
    ) -> None:
        if account.trading_mode is not TradingMode.PAPER:
            raise PaperAdapterError("PaperTradingService requires a PAPER account")
        self._account = account
        self._broker = broker
        self._reference_prices = dict(reference_prices or {})
        self._cost_model = cost_model or PaperCostModel()
        self._clock = clock
        self._repository = repository
        # Restart recovery: restore the funds ledger from durable state when
        # available; otherwise seed from explicit starting capital.
        restored = (
            repository.load_funds(account.account_id)
            if repository is not None
            else None
        )
        self._funds = restored or PaperFunds(
            account_id=account.account_id, available_cash=account.starting_capital
        )
        self._outcomes: list[PaperFillOutcome] = []
        self._sequence = 0

    # ------------------------------------------------------------------ reads
    @property
    def account(self) -> PaperAccount:
        return self._account

    @property
    def funds(self) -> PaperFunds:
        return self._funds

    @property
    def outcomes(self) -> tuple[PaperFillOutcome, ...]:
        return tuple(self._outcomes)

    @property
    def cost_model(self) -> PaperCostModel:
        return self._cost_model

    async def positions(self) -> list[BrokerPositionSnapshot]:
        """PAPER-labeled positions from the broker's authoritative fill trail."""
        return await self._broker.get_positions()

    def set_reference_price(
        self, instrument_id: UUID, reference: PaperReferencePrice
    ) -> None:
        """Advance the simulated market for one instrument (deterministic replay step)."""
        self._reference_prices[instrument_id] = reference
        self._broker.set_reference_price(instrument_id, reference)

    # ------------------------------------------------------------------ submit
    async def submit(
        self,
        *,
        instrument_id: UUID,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> PaperFillOutcome:
        self._guard_account()
        if quantity <= 0:
            return self._reject_without_fill(
                instrument_id, side, quantity, client_order_id, "quantity must be positive"
            )
        if side not in (OrderSide.BUY, OrderSide.SELL):
            return self._reject_without_fill(
                instrument_id, side, quantity, client_order_id, f"unsupported side: {side}"
            )

        client_order_id = client_order_id or self._next_client_order_id()
        order_id = paper_order_id(self._account.account_id, client_order_id)
        request = BrokerOrderRequest(
            broker_account_id=self._account.account_id,
            instrument_id=instrument_id,
            trading_mode=TradingMode.PAPER,
            client_order_id=client_order_id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            risk_approval_id=f"paper-{self._account.paper_run_id}",
            limit_price=limit_price,
            metadata={"order_id": str(order_id)},
        )

        reference = self._reference_prices.get(instrument_id)

        # Pre-submission funds guard (service-level, broker is funds-unaware).
        if side is OrderSide.BUY and reference is not None:
            if not self._can_afford(request, reference, quantity):
                return self._reject_without_fill(
                    instrument_id, side, quantity, client_order_id,
                    "insufficient available funds",
                )

        fill_price, reason, occurred_at = await self._submit_and_collect(request)
        if fill_price is None:
            outcome = PaperFillOutcome(
                client_order_id=client_order_id,
                order_id=order_id,
                side=side,
                instrument_id=instrument_id,
                quantity=quantity,
                fill_price=None,
                effective_price=None,
                commission=Decimal("0"),
                net_cash=Decimal("0"),
                accepted=False,
                reason=reason or "order rejected by paper broker",
                occurred_at=occurred_at,
            )
            self._outcomes.append(outcome)
            return outcome

        # Apply deterministic cost model + update funds ledger.
        effective = apply_slippage(fill_price, side.value, self._cost_model)
        notional = effective * Decimal(quantity)
        commission = commission_amount(notional, self._cost_model)
        if side is OrderSide.BUY:
            total_debit = notional + commission
            net_cash = -total_debit
            try:
                self._funds = self._funds.reserve(total_debit).settle_buy(total_debit)
            except ValueError as exc:
                # Funds changed between pre-flight and settlement (defensive).
                return self._reject_without_fill(
                    instrument_id, side, quantity, client_order_id, str(exc)
                )
            self._persist_funds()
        else:
            net_cash = notional - commission
            self._funds = self._funds.credit_sell(net_cash)
            self._persist_funds()

        outcome = PaperFillOutcome(
            client_order_id=client_order_id,
            order_id=order_id,
            side=side,
            instrument_id=instrument_id,
            quantity=quantity,
            fill_price=fill_price,
            effective_price=effective,
            commission=commission,
            net_cash=net_cash,
            accepted=True,
            reason=None,
            occurred_at=occurred_at,
        )
        self._outcomes.append(outcome)
        return outcome

    # ------------------------------------------------------------------ internals
    def _persist_funds(self) -> None:
        if self._repository is not None:
            self._repository.save_funds(self._funds)

    def _guard_account(self) -> None:
        if self._account.status is not PaperAccountStatus.ACTIVE:
            raise PaperAdapterError(f"paper account is not active: {self._account.status}")

    def _next_client_order_id(self) -> str:
        self._sequence += 1
        return f"paper-{self._account.account_id}-{self._sequence}"

    def _can_afford(
        self, request: BrokerOrderRequest, reference: PaperReferencePrice, quantity: int
    ) -> bool:
        try:
            decision = decide_fill(request, reference)
        except PaperAdapterError:
            return True  # unsupported type -> broker rejects; no cash commitment
        if not decision.fills or decision.fill_price is None:
            return True  # non-executable -> broker rejects; no cash commitment
        effective = apply_slippage(decision.fill_price, "BUY", self._cost_model)
        notional = effective * Decimal(quantity)
        commission = commission_amount(notional, self._cost_model)
        return (notional + commission) <= self._funds.available_cash

    async def _submit_and_collect(
        self, request: BrokerOrderRequest
    ) -> tuple[Decimal | None, str | None, datetime]:
        response = await self._broker.submit_order(request)
        events = self._broker.pending_events()
        fill_price: Decimal | None = None
        reason: str | None = None
        occurred_at = self._clock()
        for ev in events:
            occurred_at = ev.occurred_at
            if ev.event_type is OrderEventType.FILL:
                raw = ev.metadata.get("paper_fill_price")
                if raw is not None:
                    fill_price = Decimal(str(raw))
            elif ev.event_type is OrderEventType.REJECTED:
                reason = ev.reason
        if fill_price is None and reason is None:
            reason = response.reason or "order rejected"
        return fill_price, reason, occurred_at

    def _reject_without_fill(
        self,
        instrument_id: UUID,
        side: OrderSide,
        quantity: int,
        client_order_id: str | None,
        reason: str,
    ) -> PaperFillOutcome:
        client_order_id = client_order_id or self._next_client_order_id()
        order_id = paper_order_id(self._account.account_id, client_order_id)
        outcome = PaperFillOutcome(
            client_order_id=client_order_id,
            order_id=order_id,
            side=side,
            instrument_id=instrument_id,
            quantity=quantity,
            fill_price=None,
            effective_price=None,
            commission=Decimal("0"),
            net_cash=Decimal("0"),
            accepted=False,
            reason=reason,
            occurred_at=self._clock(),
        )
        self._outcomes.append(outcome)
        return outcome
