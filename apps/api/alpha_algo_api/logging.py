from __future__ import annotations

import logging
from typing import Any

from alpha_algo_api.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")


def log_request_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(
        "api_request",
        extra={
            "event": event,
            **fields,
        },
    )
