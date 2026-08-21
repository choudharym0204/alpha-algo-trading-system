from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

from alpha_algo_api.logging import log_request_event
from alpha_algo_api.observability import (
    record_http_end,
    record_http_request,
    record_http_start,
)
from alpha_algo_observability import begin_trace, parse_traceparent, start_span

REQUEST_ID_HEADER = "x-request-id"
TRACEPARENT_HEADER = "traceparent"
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

    # Trace adoption: link local spans to an inbound W3C traceparent if valid.
    incoming = parse_traceparent(request.headers.get(TRACEPARENT_HEADER))
    trace_ctx = begin_trace(
        incoming.trace_id if incoming else None,
        sampled=incoming.sampled if incoming else True,
    )
    request.state.trace_id = trace_ctx.trace_id

    started_at = time.perf_counter()
    record_http_start()
    try:
        with start_span(
            "http_request",
            attributes={
                "http.method": request.method,
                "http.route": request.url.path,
                "request_id": request_id,
            },
        ) as span:
            request.state.span_id = span.span_id
            response = await call_next(request)
            span.set_status(
                "error" if response.status_code >= 500 else "ok",
                error=response.status_code >= 500,
            )
    finally:
        record_http_end()

    duration_s = time.perf_counter() - started_at
    record_http_request(request.method, response.status_code, duration_s)
    response.headers[REQUEST_ID_HEADER] = request_id

    span_id = getattr(request.state, "span_id", None)
    log_request_event(
        logger,
        "request_completed",
        request_id=request_id,
        trace_id=request.state.trace_id,
        span_id=span_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_s * 1000, 3),
    )
    return response
