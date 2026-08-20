"""Structured execution-engine errors + failure classification (Phase 9).

Failure classes drive the retry policy: only TRANSIENT_FAILURE is safely
retryable; TIMEOUT and UNKNOWN_EXTERNAL_STATE are ambiguous and must NOT be
blind-retried. VALIDATION/AUTH/PROVIDER/INTERNAL are permanent (no retry).
"""

from __future__ import annotations

from enum import StrEnum


class FailureClass(StrEnum):
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    AUTH_FAILURE = "AUTH_FAILURE"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    TIMEOUT = "TIMEOUT"
    PROVIDER_REJECTION = "PROVIDER_REJECTION"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


RETRYABLE_FAILURE_CLASSES = frozenset({FailureClass.TRANSIENT_FAILURE})


class ExecutionError(Exception):
    """Base class for all execution-engine errors (carries a failure class)."""

    failure_class: FailureClass = FailureClass.INTERNAL_FAILURE

    def __init__(self, message: str, *, failure_class: FailureClass | None = None) -> None:
        super().__init__(message)
        if failure_class is not None:
            self.failure_class = failure_class


class ExecutionValidationError(ExecutionError):
    """Request/order data is missing or inconsistent — permanent, no retry."""

    failure_class = FailureClass.VALIDATION_FAILURE


class ExecutionAuthError(ExecutionError):
    """Authentication/authorization failure — permanent until corrected."""

    failure_class = FailureClass.AUTH_FAILURE


class ExecutionTransientError(ExecutionError):
    """Transient failure — the only safely-retryable class."""

    failure_class = FailureClass.TRANSIENT_FAILURE


class ExecutionTimeoutError(ExecutionError):
    """Submission/response timeout — ambiguous, must NOT be blind-retried."""

    failure_class = FailureClass.TIMEOUT


class ExecutionProviderRejection(ExecutionError):
    """The provider definitively rejected the order."""

    failure_class = FailureClass.PROVIDER_REJECTION


class ExecutionUnknownState(ExecutionError):
    """External execution state is unknown — requires verification."""

    failure_class = FailureClass.UNKNOWN_EXTERNAL_STATE


class ExecutionInternalError(ExecutionError):
    """Internal failure — rollback and surface safely."""

    failure_class = FailureClass.INTERNAL_FAILURE


# Convenience aliases used across the engine.
ExecutionRejected = ExecutionProviderRejection


class DuplicateExecutionError(ExecutionError):
    """A duplicate execution request was detected (idempotent no-op)."""

    failure_class = FailureClass.VALIDATION_FAILURE


class ExecutionNotFoundError(ExecutionError):
    """The target order/attempt does not exist."""

    failure_class = FailureClass.VALIDATION_FAILURE


def classify(exception: Exception) -> FailureClass:
    """Classify any exception into a failure class for retry decisions."""
    if isinstance(exception, ExecutionError):
        return exception.failure_class
    if isinstance(exception, TimeoutError):
        return FailureClass.TIMEOUT
    return FailureClass.INTERNAL_FAILURE
