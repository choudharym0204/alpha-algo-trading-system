"""Phase 8 OMS — deterministic order identity tests."""

from uuid import UUID, uuid4

from alpha_algo_oms.identity import (
    build_order_identity,
    compute_order_identity_key,
    make_client_order_id,
)

from oms_test_support import make_intent


def test_identity_key_is_deterministic():
    i = make_intent()
    k1 = compute_order_identity_key(
        orchestration_id=i.orchestration_id,
        signal_id=i.signal_id,
        strategy_id=i.strategy_id,
        account_id=i.account_id,
        instrument_id=i.instrument_id,
        side=i.action,
        quantity=int(i.quantity),
        order_type=i.order_type,
        trading_mode=i.trading_mode,
        risk_approval_id=str(i.approval_id),
    )
    k2 = compute_order_identity_key(
        orchestration_id=i.orchestration_id,
        signal_id=i.signal_id,
        strategy_id=i.strategy_id,
        account_id=i.account_id,
        instrument_id=i.instrument_id,
        side=i.action,
        quantity=int(i.quantity),
        order_type=i.order_type,
        trading_mode=i.trading_mode,
        risk_approval_id=str(i.approval_id),
    )
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


def test_identity_key_changes_with_quantity():
    i = make_intent(quantity="10")
    j = make_intent(quantity="20")
    assert compute_order_identity_key(
        orchestration_id=i.orchestration_id, signal_id=i.signal_id,
        strategy_id=i.strategy_id, account_id=i.account_id,
        instrument_id=i.instrument_id, side=i.action, quantity=10,
        order_type=i.order_type, trading_mode=i.trading_mode,
        risk_approval_id=str(i.approval_id),
    ) != compute_order_identity_key(
        orchestration_id=j.orchestration_id, signal_id=j.signal_id,
        strategy_id=j.strategy_id, account_id=j.account_id,
        instrument_id=j.instrument_id, side=j.action, quantity=20,
        order_type=j.order_type, trading_mode=j.trading_mode,
        risk_approval_id=str(j.approval_id),
    )


def test_identity_key_changes_with_instrument():
    i = make_intent()
    key = lambda inst: compute_order_identity_key(
        orchestration_id=i.orchestration_id, signal_id=i.signal_id,
        strategy_id=i.strategy_id, account_id=i.account_id,
        instrument_id=inst, side=i.action, quantity=int(i.quantity),
        order_type=i.order_type, trading_mode=i.trading_mode,
        risk_approval_id=str(i.approval_id),
    )
    assert key(i.instrument_id) != key(uuid4())


def test_identity_key_changes_with_side():
    i = make_intent()
    key = lambda side: compute_order_identity_key(
        orchestration_id=i.orchestration_id, signal_id=i.signal_id,
        strategy_id=i.strategy_id, account_id=i.account_id,
        instrument_id=i.instrument_id, side=side, quantity=int(i.quantity),
        order_type=i.order_type, trading_mode=i.trading_mode,
        risk_approval_id=str(i.approval_id),
    )
    assert key("BUY") != key("SELL")


def test_identity_key_changes_with_approval():
    i = make_intent()
    key = lambda approval: compute_order_identity_key(
        orchestration_id=i.orchestration_id, signal_id=i.signal_id,
        strategy_id=i.strategy_id, account_id=i.account_id,
        instrument_id=i.instrument_id, side=i.action, quantity=int(i.quantity),
        order_type=i.order_type, trading_mode=i.trading_mode,
        risk_approval_id=approval,
    )
    assert key(str(i.approval_id)) != key(str(uuid4()))


def test_client_order_id_is_deterministic():
    assert make_client_order_id("abc") == "ord-abc"
    assert make_client_order_id("abc") == make_client_order_id("abc")


def test_build_order_identity_maps_all_fields():
    i = make_intent()
    oid = uuid4()
    ident = build_order_identity(i, internal_order_id=oid, quantity=10)
    assert ident.internal_order_id == oid
    assert ident.client_order_id == f"ord-{i.orchestration_id}"
    assert ident.correlation_id == str(i.correlation_id)
    assert ident.broker_order_id is None
    assert len(ident.order_identity_key) == 64
    assert isinstance(ident.internal_order_id, UUID)


def test_build_order_identity_quantity_matches_key():
    i = make_intent(quantity="10")
    ident10 = build_order_identity(i, internal_order_id=uuid4(), quantity=10)
    ident20 = build_order_identity(i, internal_order_id=uuid4(), quantity=20)
    assert ident10.order_identity_key != ident20.order_identity_key
