from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

from alpha_algo_api.logging import log_request_event

REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger("alpha_algo_api.requests")


def resolve_request_id(request: Request) -> str:
    """Return a safe request id: the inbound header if it matches a safe pattern,
    otherwise a freshly generated one (prevents header/log injection)."""
    header = request.headers.get(REQUEST_ID_HEADER)
    if header and _SAFE_REQUEST_ID.match(header):
        return header
    return f"req_{uuid4().hex}"


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = resolve_request_id(request)
    request.state.request_id = request_id
    started_at = time.perf_counter()

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id

    log_request_event(
        logger,
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
    )
    return response
