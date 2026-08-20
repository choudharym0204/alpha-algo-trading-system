"""Structured, non-leaky P&L Engine errors (Phase 13)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class PnlError(Exception):
    code = "PNL_ERROR"


class PnlValidationError(PnlError):
    code = "PNL_VALIDATION_ERROR"


class PnlDataError(PnlError):
    """A required source (position / price / cost basis) is missing or unusable."""

    code = "PNL_DATA_ERROR"


class PnlModeError(PnlError):
    """LIVE or unknown trading mode (fail-closed)."""

    code = "PNL_MODE_ERROR"


class PnlOverCloseError(PnlError):
    """SELL exceeds open long quantity (Phase 11 already rejects this)."""

    code = "PNL_OVER_CLOSE_ERROR"


class PnlPersistenceError(PnlError):
    code = "PNL_PERSISTENCE_ERROR"


class DuplicateExecutionError(PnlError):
    """Internal sentinel: a P&L event already exists for this execution identity."""

    code = "DUPLICATE_EXECUTION"


class PnlConflictError(PnlError):
    """Same execution identity but a different accounting payload (no overwrite)."""

    code = "PNL_CONFLICT"


class PnlRejectedError(PnlError):
    """The accounting effect was rejected (invalid input / over-close / halt)."""

    code = "PNL_REJECTED"


@dataclass(frozen=True)
class PnlErrorDetail:
    code: str
    message: str
    account_id: UUID | None = None


def to_error_detail(exc: PnlError) -> PnlErrorDetail:
    return PnlErrorDetail(code=exc.code, message=str(exc), account_id=getattr(exc, "account_id", None))
