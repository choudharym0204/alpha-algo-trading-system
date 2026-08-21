"""Error normalization (Phase 20 §39).

Maps diverse failure signals (API error codes, exception types, status codes)
into a small, stable set of failure classes so metrics/dashboards/alerts can
aggregate without high-cardinality raw exception strings. Provider-specific
details stay in structured log/trace fields, never in metric labels.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["FailureClass", "classify_error", "classify_status_code"]


class FailureClass(str, Enum):
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    DATABASE_ERROR = "DATABASE_ERROR"
    BROKER_ERROR = "BROKER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STATE_CONFLICT = "STATE_CONFLICT"
    UNKNOWN = "UNKNOWN"


_STATUS_MAP: dict[int, FailureClass] = {
    401: FailureClass.AUTHENTICATION_FAILURE,
    403: FailureClass.AUTHORIZATION_FAILURE,
    422: FailureClass.VALIDATION_FAILURE,
    429: FailureClass.RATE_LIMIT,
    503: FailureClass.PROVIDER_UNAVAILABLE,
    504: FailureClass.TIMEOUT,
    408: FailureClass.TIMEOUT,
    409: FailureClass.STATE_CONFLICT,
}

# Lower-case substrings of API error codes that map to a failure class.
_CODE_MAP: list[tuple[str, FailureClass]] = [
    ("auth", FailureClass.AUTHENTICATION_FAILURE),
    ("forbidden", FailureClass.AUTHORIZATION_FAILURE),
    ("permission", FailureClass.AUTHORIZATION_FAILURE),
    ("validation", FailureClass.VALIDATION_FAILURE),
    ("rate", FailureClass.RATE_LIMIT),
    ("timeout", FailureClass.TIMEOUT),
    ("database", FailureClass.DATABASE_ERROR),
    ("db_", FailureClass.DATABASE_ERROR),
    ("broker", FailureClass.BROKER_ERROR),
    ("network", FailureClass.NETWORK_ERROR),
    ("provider", FailureClass.PROVIDER_UNAVAILABLE),
    ("unavailable", FailureClass.PROVIDER_UNAVAILABLE),
    ("conflict", FailureClass.STATE_CONFLICT),
    ("duplicate", FailureClass.STATE_CONFLICT),
]


def classify_status_code(status_code: int) -> FailureClass:
    if status_code >= 500:
        return _STATUS_MAP.get(status_code, FailureClass.PROVIDER_UNAVAILABLE)
    return _STATUS_MAP.get(status_code, FailureClass.UNKNOWN)


def classify_error(error: BaseException | None, *, code: str | None = None, status_code: int | None = None) -> FailureClass:
    """Classify an error. Priority: status code -> API code -> exception type."""
    if status_code is not None:
        return classify_status_code(status_code)

    if code:
        lowered = code.lower()
        for fragment, failure_class in _CODE_MAP:
            if fragment in lowered:
                return failure_class

    if error is None:
        return FailureClass.UNKNOWN

    name = error.__class__.__name__
    lowered_name = name.lower()
    if "timeout" in lowered_name:
        return FailureClass.TIMEOUT
    if "broker" in lowered_name:
        return FailureClass.BROKER_ERROR
    if "database" in lowered_name or "db" in lowered_name:
        return FailureClass.DATABASE_ERROR
    if "network" in lowered_name or "connection" in lowered_name:
        return FailureClass.NETWORK_ERROR
    if "validation" in lowered_name:
        return FailureClass.VALIDATION_FAILURE
    if "conflict" in lowered_name or "duplicate" in lowered_name:
        return FailureClass.STATE_CONFLICT

    # Fall back to the exception's own status/code if it exposes one.
    for attr in ("status_code", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return classify_status_code(value)
        if isinstance(value, str):
            for fragment, failure_class in _CODE_MAP:
                if fragment in value.lower():
                    return failure_class

    return FailureClass.UNKNOWN
