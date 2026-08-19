from __future__ import annotations

import os

from dotenv import load_dotenv

from alpha_algo_shared.db import Base

# Load .env so that DATABASE_URL (and other vars) are visible to os.getenv.
# This keeps migration execution parity with the pydantic-settings app config.
load_dotenv()


DEFAULT_SQLALCHEMY_URL = (
    "postgresql+psycopg://alpha_algo_app:replace-with-local-dev-password@"
    "localhost:5432/alpha_algo"
)

target_metadata = Base.metadata


def build_sqlalchemy_url(explicit_url: str | None = None) -> str:
    if explicit_url:
        return explicit_url

    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    return DEFAULT_SQLALCHEMY_URL

