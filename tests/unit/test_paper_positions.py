from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_broker_adapters import (
    BrokerCredentialsRef,
    BrokerOrderRequest,
    BrokerPositionSnapshot,
    OrderSide,
    OrderType,
    TradingMode,
)
from alpha_algo_paper_trading import (
    PaperBrokerAdapter,
    PaperPosition,
    PaperReferencePrice,
    paper_order_id,
)

FIXED_NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
BROKER_ACCOUNT_ID = UUID("10000000-0000-0000-0000-000000000001")
INSTRUMENT_A = UUID("20000000-0000-0000-0000-000000000002")
INSTRUMENT_B = UUID("20000000-0000-0000-0000-000000000003")
OTHER_ACCOUNT = UUID("10000000-0000-0000-0000-000000000099")

REFERENCE_A = PaperReferencePrice(
    instrument_id=INSTRUMENT_A,
    last=Decimal("100.00"),
    bid=Decimal("99.50"),
    ask=Decimal("100.50"),
    reference_at=FIXED_NOW,
)
REFERENCE_B = PaperReferencePrice(
    instrument_id=INSTRUMENT_B,
    last=Decimal("50.00"),
    bid=Decimal("49.50"),
    ask=Decimal("50.50"),
    reference_at=FIXED_NOW,
)


def _request(
    *,
    instrument_id: UUID = INSTRUMENT_A,
    side: OrderSide = OrderSide.BUY,
    quantity: int = 10,
    client_order_id: str = "pos-1",
    broker_account_id: UUID = BROKER_ACCOUNT_ID,
) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        broker_account_id=broker_account_id,
        instrument_id=instrument_id,
        trading_mode=TradingMode.PAPER,
        client_order_id=client_order_id,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        risk_approval_id="risk-approval-1",
        metadata={
            "order_id": str(paper_order_id(broker_account_id, client_order_id)),
        },
    )


def _adapter() -> PaperBrokerAdapter:
    adapter = PaperBrokerAdapter(
        clock=lambda: FIXED_NOW,
        reference_prices={INSTRUMENT_A: REFERENCE_A, INSTRUMENT_B: REFERENCE_B},
    )
    asyncio.run(
        adapter.connect(
            BrokerCredentialsRef(
                broker_name="paper",
                account_identifier="paper-account-1",
                secret_ref="__MUST_NOT_BE_READ__",
            )
        )
    )
    return adapter


def _submit(adapter: PaperBrokerAdapter, request: BrokerOrderRequest) -> None:
    asyncio.run(adapter.submit_order(request))
    adapter.pending_events()  # drain


def _positions(adapter: PaperBrokerAdapter) -> list[BrokerPositionSnapshot]:
    return asyncio.run(adapter.get_positions())


def test_no_positions_before_any_fill() -> None:
    adapter = _adapter()
    assert _positions(adapter) == []


def test_aggregates_net_quantity_and_weighted_average_price() -> None:
    adapter = _adapter()
    _submit(adapter, _request(quantity=10, client_order_id="pos-1"))  # BUY 10 @ 100
    _submit(adapter, _request(quantity=10, client_order_id="pos-2"))  # BUY 10 @ 100

    snapshots = _positions(adapter)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.trading_mode is TradingMode.PAPER
    assert snapshot.quantity == Decimal("20")
    assert snapshot.average_price == Decimal("100.00")
    assert snapshot.captured_at.tzinfo is not None
    assert snapshot.raw_payload["fill_source"] == "paper_simulator"


def test_sell_reduces_net_quantity() -> None:
    adapter = _adapter()
    _submit(adapter, _request(quantity=10, client_order_id="pos-1"))  # BUY 10
    _submit(
        adapter,
        _request(side=OrderSide.SELL, quantity=4, client_order_id="pos-2"),
    )  # SELL 4

    snapshots = _positions(adapter)
    assert len(snapshots) == 1
    assert snapshots[0].quantity == Decimal("6")


def test_positions_are_separated_per_instrument() -> None:
    adapter = _adapter()
    _submit(adapter, _request(quantity=10, client_order_id="pos-1"))
    _submit(
        adapter,
        _request(instrument_id=INSTRUMENT_B, quantity=5, client_order_id="pos-2"),
    )

    snapshots = _positions(adapter)
    assert len(snapshots) == 2
    by_instrument = {s.instrument_id: s for s in snapshots}
    assert by_instrument[INSTRUMENT_A].quantity == Decimal("10")
    assert by_instrument[INSTRUMENT_B].quantity == Decimal("5")


def test_positions_are_separated_per_account() -> None:
    adapter = _adapter()
    _submit(adapter, _request(quantity=10, client_order_id="pos-1"))
    _submit(
        adapter,
        _request(
            quantity=3,
            client_order_id="pos-other-1",
            broker_account_id=OTHER_ACCOUNT,
        ),
    )

    snapshots = _positions(adapter)
    assert len(snapshots) == 2  # one per account, same instrument
    by_account = {s.broker_account_id: s for s in snapshots}
    assert by_account[BROKER_ACCOUNT_ID].quantity == Decimal("10")
    assert by_account[OTHER_ACCOUNT].quantity == Decimal("3")


def test_average_price_uses_documented_decimal_quantum() -> None:
    adapter = _adapter()
    # Buy fills at reference.last = 100.00 for both orders; weighted average of
    # 4 units at 100.00 is exactly 100.00 (quantum-invariant).
    _submit(adapter, _request(quantity=3, client_order_id="pos-1"))
    _submit(adapter, _request(quantity=1, client_order_id="pos-2"))

    snapshots = _positions(adapter)
    assert snapshots[0].average_price == Decimal("100.00")


def test_mixed_buy_sell_average_price_is_mean_fill_price() -> None:
    """M2 pin: average_price is the quantity-weighted mean of ALL fills (buys
    and sells), not the average-cost basis of the remaining net position.
    BUY 10 @ 100.00 then SELL 4 @ 99.50 -> net 6 units at 99.85714286.
    """
    from alpha_algo_paper_trading import PaperOrderBook

    book = PaperOrderBook(clock=lambda: FIXED_NOW)
    sell_reference = PaperReferencePrice(
        instrument_id=INSTRUMENT_A,
        last=Decimal("99.50"),
        bid=Decimal("99.40"),
        ask=Decimal("99.60"),
        reference_at=FIXED_NOW,
    )
    book.submit(
        _request(quantity=10, client_order_id="pos-m2-1"), reference=REFERENCE_A
    )
    book.submit(
        _request(
            side=OrderSide.SELL, quantity=4, client_order_id="pos-m2-2"
        ),
        reference=sell_reference,
    )

    positions = book.positions(BROKER_ACCOUNT_ID)
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("6")
    assert positions[0].average_price == Decimal("99.85714286")


def test_full_round_trip_drops_flat_position() -> None:
    """L1 pin: BUY 10 / SELL 10 leaves a zero-net position, which is not
    reported."""
    from alpha_algo_paper_trading import PaperOrderBook

    book = PaperOrderBook(clock=lambda: FIXED_NOW)
    book.submit(
        _request(quantity=10, client_order_id="pos-rt-1"), reference=REFERENCE_A
    )
    book.submit(
        _request(
            side=OrderSide.SELL, quantity=10, client_order_id="pos-rt-2"
        ),
        reference=REFERENCE_A,
    )

    assert book.positions(BROKER_ACCOUNT_ID) == ()


def test_fill_decision_validates_its_invariants() -> None:
    """L2 pin: a rejection decision must carry zero quantity and no price; a
    fill decision must carry positive price and quantity."""
    from decimal import Decimal as D

    from alpha_algo_paper_trading import FillDecision

    with pytest.raises(ValueError, match="zero fill_quantity"):
        FillDecision(fills=False, fill_price=None, fill_quantity=D("5"))
    with pytest.raises(ValueError, match="fill_price=None"):
        FillDecision(fills=False, fill_price=D("1"), fill_quantity=D("0"))
    with pytest.raises(ValueError, match="positive fill_price"):
        FillDecision(fills=True, fill_price=D("0"), fill_quantity=D("5"))
    with pytest.raises(ValueError, match="positive fill_quantity"):
        FillDecision(fills=True, fill_price=D("1"), fill_quantity=D("0"))


def test_reference_price_rejects_last_outside_spread() -> None:
    """L3 pin: when both bid and ask legs are present, last must lie within
    the spread (a MARKET fill can never cross the quoted legs)."""
    with pytest.raises(ValueError, match="within the bid/ask spread"):
        PaperReferencePrice(
            instrument_id=INSTRUMENT_A,
            last=Decimal("100.00"),
            bid=Decimal("99.00"),
            ask=Decimal("99.50"),
            reference_at=FIXED_NOW,
        )


def test_reference_price_rejects_incoherent_legs() -> None:
    with pytest.raises(ValueError, match="bid cannot exceed ask"):
        PaperReferencePrice(
            instrument_id=INSTRUMENT_A,
            last=Decimal("100.00"),
            bid=Decimal("101.00"),
            ask=Decimal("100.50"),
            reference_at=FIXED_NOW,
        )
    with pytest.raises(ValueError, match="last must be positive"):
        PaperReferencePrice(
            instrument_id=INSTRUMENT_A,
            last=Decimal("0"),
            reference_at=FIXED_NOW,
        )


def test_average_price_quantizes_repeating_decimal() -> None:
    """The book aggregates from the fill trail with exact Decimal division,
    quantized to AVERAGE_PRICE_QUANTUM (ROUND_HALF_EVEN). The adapter's v1
    snapshot passes one reference per instrument, but the book itself accepts
    per-submit references, so two different fill prices are representable.
    """
    from alpha_algo_paper_trading import PaperOrderBook

    book = PaperOrderBook(clock=lambda: FIXED_NOW)
    high = PaperReferencePrice(
        instrument_id=INSTRUMENT_A,
        last=Decimal("100.01"),
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        reference_at=FIXED_NOW,
    )
    # BUY 1 @ 100.00 then BUY 2 @ 100.01 -> weighted avg 100.00666...
    book.submit(_request(quantity=1, client_order_id="pos-q-1"), reference=REFERENCE_A)
    book.submit(_request(quantity=2, client_order_id="pos-q-2"), reference=high)

    positions = book.positions(BROKER_ACCOUNT_ID)
    assert positions[0].average_price == Decimal("100.00666667")
    assert positions[0].average_price.as_tuple().exponent == -8


def test_paper_position_type_refuses_live_mode() -> None:
    with pytest.raises(ValueError, match="PAPER"):
        PaperPosition(
            broker_account_id=BROKER_ACCOUNT_ID,
            instrument_id=INSTRUMENT_A,
            trading_mode=TradingMode.LIVE,
            quantity=Decimal("10"),
            average_price=Decimal("100.00"),
            captured_at=FIXED_NOW,
        )
