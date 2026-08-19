"""Runtime configuration (pydantic-settings).

Reads environment variables and an optional ``.env`` file. Security-critical
values are validated fail-closed: the app refuses to start in production with
placeholder secrets, and LIVE trading can never be enabled while the global
halt is active.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from alpha_algo_api.security.secret import is_placeholder

AppEnvironment = Literal["development", "test", "staging", "production"]
TradingMode = Literal["BACKTEST", "PAPER", "LIVE"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime identity
    app_name: str = "alpha-algo-trading-system"
    app_env: AppEnvironment = "development"
    log_level: str = "INFO"
    structured_logs: bool = True

    # Network
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = (
        "postgresql+psycopg://alpha_algo_app:replace-with-local-dev-password"
        "@localhost:5432/alpha_algo"
    )

    # Database runtime (Phase 2)
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_echo: bool = False
    db_connect_timeout: int = 5
    db_statement_timeout_ms: int = 30000
    db_startup_check_enabled: bool = True
    db_startup_check_timeout_seconds: int = 5
    db_retry_attempts: int = 3
    db_retry_delay_seconds: float = 0.5
    db_dispose_on_shutdown: bool = True

    # Security
    secret_key: str = "dev-only-insecure-secret-key-change-me"
    jwt_issuer: str = "alpha-algo-local"
    jwt_audience: str = "alpha-algo-users"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_minutes: int = 10080
    credential_encryption_key: str = "dev-only-insecure-encryption-key-change-me"
    password_hash_scheme: str = "argon2id"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120

    # CORS (comma-separated list of allowed origins)
    cors_allowed_origins: str = "http://localhost:3000"

    # Trust proxy headers (X-Forwarded-For). Enable only behind a trusted proxy
    # that overwrites/strips client-supplied forwarded headers.
    trust_proxy_headers: bool = False

    # Trading safety (fail-closed)
    live_trading_enabled: bool = False
    global_trading_halt: bool = True
    default_trading_mode: TradingMode = "PAPER"

    # Market data (Phase 3)
    market_data_enabled: bool = False
    market_data_provider: str = "fake"
    market_data_symbols: str = ""  # comma-separated instrument symbols
    market_data_stale_after_seconds: int = 5
    market_data_heartbeat_seconds: int = 15
    market_data_heartbeat_timeout_seconds: int = 45
    market_data_reconnect_max_attempts: int = 10
    market_data_reconnect_base_delay_seconds: float = 0.5
    market_data_reconnect_max_delay_seconds: float = 30.0
    market_data_connect_timeout_seconds: float = 10.0
    market_data_request_timeout_seconds: float = 10.0
    market_data_backpressure_queue_size: int = 10000
    market_data_drop_policy: str = "drop_newest"
    market_data_persist_enabled: bool = True
    market_data_historical_max_candles: int = 10000
    market_data_historical_page_size: int = 1000

    @property
    def market_data_symbol_list(self) -> list[str]:
        return [s.strip() for s in self.market_data_symbols.split(",") if s.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_fail_closed(self) -> "Settings":
        if self.live_trading_enabled and self.global_trading_halt:
            raise ValueError(
                "live_trading_enabled cannot be true while global_trading_halt is true."
            )
        if self.app_env == "production":
            if is_placeholder(self.secret_key):
                raise ValueError(
                    "production requires a real SECRET_KEY (got a placeholder)."
                )
            if is_placeholder(self.credential_encryption_key):
                raise ValueError(
                    "production requires a real CREDENTIAL_ENCRYPTION_KEY (got a placeholder)."
                )
            if is_placeholder(self.database_url):
                raise ValueError(
                    "production requires a real DATABASE_URL (got a placeholder)."
                )
        if self.db_pool_size < 1:
            raise ValueError("db_pool_size must be >= 1.")
        if self.db_statement_timeout_ms < 0:
            raise ValueError("db_statement_timeout_ms must be >= 0.")
        if self.db_retry_attempts < 1:
            raise ValueError("db_retry_attempts must be >= 1.")
        if self.market_data_stale_after_seconds <= 0:
            raise ValueError("market_data_stale_after_seconds must be > 0.")
        if self.market_data_reconnect_max_attempts < 0:
            raise ValueError("market_data_reconnect_max_attempts must be >= 0.")
        if self.market_data_backpressure_queue_size < 1:
            raise ValueError("market_data_backpressure_queue_size must be >= 1.")
        if self.market_data_drop_policy not in {"drop_newest", "drop_oldest"}:
            raise ValueError(
                "market_data_drop_policy must be 'drop_newest' or 'drop_oldest'."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Clear the cached settings (used by tests that mutate the environment)."""
    get_settings.cache_clear()
