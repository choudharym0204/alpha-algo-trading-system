from __future__ import annotations

"""Error types for the paper trading foundation.

All errors derive from :class:`PaperAdapterError` (itself a ``ValueError``),
matching the house pattern of the execution engine
(:class:`alpha_algo_execution_engine.InvalidOrderEvent`) and the risk engine
(:class:`alpha_algo_risk_engine.RiskApprovalRequired`): caller misuse and
unsupported surface area fail loud instead of degrading silently.
"""

__all__ = [
    "ClientOrderIdConflictError",
    "PaperAdapterError",
    "PaperMarketDataUnavailableError",
    "PaperModeViolationError",
    "UnsupportedOrderTypeError",
]


class PaperAdapterError(ValueError):
    """Base error for the paper trading foundation."""


class PaperModeViolationError(PaperAdapterError):
    """Raised when a non-PAPER order reaches the paper adapter.

    The paper adapter accepts only ``TradingMode.PAPER`` requests. Any other
    mode (including LIVE and BACKTEST) is rejected by identity check so that
    mode leakage is a loud exception rather than a silent bookkeeping bug.
    """


class PaperMarketDataUnavailableError(PaperAdapterError):
    """Raised by ``PaperBrokerAdapter.get_quote``.

    The paper broker never fetches market data: reference prices are injected
    at construction time and are never obtained from a feed or a broker.
    """


class UnsupportedOrderTypeError(PaperAdapterError):
    """Raised by the pure fill policy for order types the v1 simulator cannot
    honestly simulate (STOP and STOP_LIMIT).

    The broker-facing surface converts this into a REJECTED response plus a
    REJECTED event so the execution engine can land the order in a terminal
    state; the pure policy itself stays strict.
    """


class ClientOrderIdConflictError(PaperAdapterError):
    """Raised when a ``client_order_id`` is reused with a different payload.

    ``client_order_id`` is the idempotency key: a duplicate submission with an
    identical payload returns the stored response and enqueues no new events,
    but a duplicate with a *different* payload is a caller bug and must never
    silently return a stale response.
    """
