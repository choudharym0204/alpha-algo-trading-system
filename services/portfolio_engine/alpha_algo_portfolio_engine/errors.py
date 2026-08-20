"""Structured, non-leaky Portfolio Engine errors (Phase 12)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class PortfolioError(Exception):
    """Base class for all Portfolio Engine errors."""

    code = "PORTFOLIO_ERROR"


class PortfolioValidationError(PortfolioError):
    """Input bundle failed an intrinsic validation rule."""

    code = "PORTFOLIO_VALIDATION_ERROR"


class PortfolioIdentityError(PortfolioError):
    """Portfolio identity could not be determined (missing account_id)."""

    code = "PORTFOLIO_IDENTITY_ERROR"


class PortfolioModeError(PortfolioError):
    """Trading mode is LIVE or unknown (fail-closed)."""

    code = "PORTFOLIO_MODE_ERROR"


class PortfolioDataError(PortfolioError):
    """A required source (positions/funds/prices) is missing or unusable."""

    code = "PORTFOLIO_DATA_ERROR"


class PortfolioPersistenceError(PortfolioError):
    """A database/persistence failure occurred (transaction not committed)."""

    code = "PORTFOLIO_PERSISTENCE_ERROR"


class DuplicateSnapshotError(PortfolioError):
    """Internal sentinel: a snapshot for the same (account, mode, snapshot_at)
    already exists (unique-constraint race). Resolved to an idempotent result."""

    code = "DUPLICATE_SNAPSHOT"


@dataclass(frozen=True)
class PortfolioErrorDetail:
    """Serializable, safe error envelope for API/observability boundaries."""

    code: str
    message: str
    account_id: UUID | None = None


def to_error_detail(exc: PortfolioError) -> PortfolioErrorDetail:
    return PortfolioErrorDetail(
        code=exc.code,
        message=str(exc),
        account_id=getattr(exc, "account_id", None),
    )
