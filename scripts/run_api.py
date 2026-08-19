"""ASGI server entrypoint for the Alpha Algo Trading System API.

Adds the monorepo package roots to ``sys.path`` and starts uvicorn, mirroring
the path bootstrap used by the test suite (``tests/conftest.py``).

Run from the repository root:

    python scripts/run_api.py

Or directly:

    uvicorn alpha_algo_api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT,
    ROOT / "apps" / "api",
    ROOT / "packages" / "shared",
    ROOT / "packages" / "contracts",
    ROOT / "packages" / "strategies",
    ROOT / "packages" / "indicators",
    ROOT / "packages" / "broker_adapters",
    ROOT / "backtesting",
    ROOT / "services",
):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import uvicorn

from alpha_algo_api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "alpha_algo_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
