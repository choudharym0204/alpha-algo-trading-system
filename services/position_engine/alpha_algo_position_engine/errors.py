"""Structured, non-leaky Position Engine errors (Phase 11).

Every failure mode maps to a distinct, catchable error type. No stack traces,
DB internals, credentials, or broker secrets are exposed through these errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class PositionError(Exception):
    """Base class for all Position Engine errors."""

    code = "POSITION_ERROR"


class PositionValidationError(PositionError):
    """The normalized fill failed an intrinsic validation rule."""

    code = "POSITION_VALIDATION_ERROR"


class PositionIdentityError(PositionError):
    """Position identity could not be determined (missing strategy_run_id)."""

    code = "POSITION_IDENTITY_ERROR"


class PositionModeError(PositionError):
    """Trading mode is LIVE or unknown (fail-closed)."""

    code = "POSITION_MODE_ERROR"


class PositionConflictError(PositionError):
    """Same execution identity, different payload — original preserved."""

    code = "POSITION_CONFLICT"

    def __init__(self, execution_id: str) -> None:
        super().__init__(
            f"position fill identity conflict for execution_id={execution_id}"
        )
        self.execution_id = execution_id


class PositionOverCloseError(PositionError):
    """A SELL would reduce a long position below zero (flip/short unsupported)."""

    code = "POSITION_OVER_CLOSE"

    def __init__(self, current: int, requested: int) -> None:
        super().__init__(
            f"over-close rejected: current={current}, requested={requested} "
            "(flip/short unsupported)"
        )
        self.current = current
        self.requested = requested


class PositionUnsupportedError(PositionError):
    """The requested semantics (short/flip) are not supported in Phase 11."""

    code = "POSITION_UNSUPPORTED"


class PositionPersistenceError(PositionError):
    """A database/persistence failure occurred (transaction not committed)."""

    code = "POSITION_PERSISTENCE_ERROR"


class PositionNotFoundError(PositionError):
    """No position exists for the requested identity."""

    code = "POSITION_NOT_FOUND"


class DuplicateApplyError(PositionError):
    """Internal sentinel: a concurrent apply already won the unique-constraint
    race for this execution identity. Caught by the engine and resolved to a
    duplicate/conflict result (never surfaced to callers)."""

    code = "DUPLICATE_APPLY"


@dataclass(frozen=True)
class PositionErrorDetail:
    """Serializable, safe error envelope for API/observability boundaries."""

    code: str
    message: str
    execution_id: str | None = None
    position_id: UUID | None = None


def to_error_detail(exc: PositionError) -> PositionErrorDetail:
    """Convert a Position error to a safe detail object (no internals leaked)."""
    return PositionErrorDetail(
        code=exc.code,
        message=str(exc),
        execution_id=getattr(exc, "execution_id", None),
        position_id=getattr(exc, "position_id", None),
    )
