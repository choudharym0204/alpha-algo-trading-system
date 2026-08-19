from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from alpha_algo_api.config import get_settings
from alpha_algo_api.db import (
    DatabaseUnavailableError,
    dispose_engine,
    verify_database_ready,
)
from alpha_algo_api.errors import (
    ApiError,
    api_error_handler,
    database_unavailable_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from alpha_algo_api.logging import configure_logging
from alpha_algo_api.middleware import request_context_middleware
from alpha_algo_api.rate_limit import rate_limit_middleware
from alpha_algo_api.routes.auth import router as auth_router
from alpha_algo_api.routes.system import router as system_router
from alpha_algo_api.routes.ws import router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings = get_settings()
    if settings.db_startup_check_enabled:
        try:
            verify_database_ready()
        except DatabaseUnavailableError as exc:
            if settings.app_env == "production":
                raise  # fail fast: refuse to serve without a database
            logger.warning("database unavailable at startup: %s", exc)
    yield
    if settings.db_dispose_on_shutdown:
        dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Alpha Algo Trading System API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware is registered innermost-first; ``add_middleware`` prepends, so
    # the effective order is: CORS (outermost) -> request-context ->
    # rate-limiting -> route. Request-id and CORS headers are therefore stamped
    # on handled error responses (401/403/404/422/429/500).
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(request_context_middleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(ws_router)
    return app


app = create_app()
