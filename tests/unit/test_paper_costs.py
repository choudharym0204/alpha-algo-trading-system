from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_paper_runtime import (
    CommissionModel,
    PaperCostModel,
    SlippageModel,
    apply_slippage,
    commission_amount,
)


def test_default_cost_model_is_zero_everything() -> None:
    model = PaperCostModel()
    assert model.slippage is SlippageModel.ZERO
    assert model.commission is CommissionModel.ZERO
    assert apply_slippage(Decimal("100"), "BUY", model) == Decimal("100")
    assert commission_amount(Decimal("10000"), model) == Decimal("0")


def test_zero_slippage_returns_price_unchanged() -> None:
    model = PaperCostModel(slippage=SlippageModel.ZERO)
    assert apply_slippage(Decimal("123.4567"), "BUY", model) == Decimal("123.4567")


def test_fixed_bps_buy_pays_more() -> None:
    model = PaperCostModel(slippage=SlippageModel.FIXED_BPS, slippage_bps=Decimal("10"))
    price = apply_slippage(Decimal("100"), "BUY", model)
    assert price == Decimal("100.1000")  # 100 * (1 + 10/10000)


def test_fixed_bps_sell_receives_less() -> None:
    model = PaperCostModel(slippage=SlippageModel.FIXED_BPS, slippage_bps=Decimal("10"))
    price = apply_slippage(Decimal("100"), "SELL", model)
    assert price == Decimal("99.9000")  # 100 * (1 - 10/10000)


def test_fixed_commission_is_deterministic() -> None:
    model = PaperCostModel(commission=CommissionModel.FIXED_PER_TRADE, commission_per_trade=Decimal("20"))
    assert commission_amount(Decimal("10000"), model) == Decimal("20.00")


def test_zero_slippage_rejects_nonzero_bps() -> None:
    with pytest.raises(ValueError, match="ZERO"):
        PaperCostModel(slippage=SlippageModel.ZERO, slippage_bps=Decimal("5"))


def test_zero_commission_rejects_nonzero_fee() -> None:
    with pytest.raises(ValueError, match="ZERO"):
        PaperCostModel(commission=CommissionModel.ZERO, commission_per_trade=Decimal("5"))


def test_cost_model_config_fingerprint() -> None:
    model = PaperCostModel(
        slippage=SlippageModel.FIXED_BPS,
        slippage_bps=Decimal("10"),
        commission=CommissionModel.FIXED_PER_TRADE,
        commission_per_trade=Decimal("20"),
    )
    cfg = model.as_config()
    assert cfg["slippage"] == "FIXED_BPS"
    assert cfg["slippage_bps"] == "10"
    assert cfg["commission"] == "FIXED_PER_TRADE"
