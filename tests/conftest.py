from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT,
    ROOT / "apps" / "api",
    ROOT / "backtesting",
    ROOT / "packages" / "broker_adapters",
    ROOT / "packages" / "contracts",
    ROOT / "packages" / "indicators",
    ROOT / "packages" / "strategies",
    ROOT / "packages" / "shared",
    ROOT / "services" / "market_data",
    ROOT / "services" / "execution_engine",
    ROOT / "services" / "risk_engine",
    ROOT / "services" / "paper_trading",
    ROOT / "services" / "strategy_engine",
    ROOT / "services" / "signal_engine",
    ROOT / "services" / "trading_engine",
    ROOT / "services" / "oms",
    ROOT / "services" / "position_engine",
    ROOT / "services" / "portfolio_engine",
    ROOT / "services" / "pnl_engine",
    ROOT / "services" / "reconciliation_engine",
    ROOT / "services" / "broker_adapters",
):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)
