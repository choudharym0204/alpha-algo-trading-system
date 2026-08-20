"""Structured, non-leaky Reconciliation Engine errors (Phase 14)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class ReconciliationError(Exception):
    code = "RECONCILIATION_ERROR"


class ReconciliationModeError(ReconciliationError):
    code = "RECONCILIATION_MODE_ERROR"


class ReconciliationValidationError(ReconciliationError):
    code = "RECONCILIATION_VALIDATION_ERROR"


class ReconciliationPersistenceError(ReconciliationError):
    code = "RECONCILIATION_PERSISTENCE_ERROR"


class ReconciliationDataError(ReconciliationError):
    code = "RECONCILIATION_DATA_ERROR"


class DuplicateDiscrepancyError(ReconciliationError):
    code = "DUPLICATE_DISCREPANCY"


class DiscrepancyConflictError(ReconciliationError):
    code = "DISCREPANCY_CONFLICT"


@dataclass(frozen=True)
class ReconciliationErrorDetail:
    code: str
    message: str
    account_id: UUID | None = None


def to_error_detail(exc: ReconciliationError) -> ReconciliationErrorDetail:
    return ReconciliationErrorDetail(
        code=exc.code, message=str(exc), account_id=getattr(exc, "account_id", None)
    )
