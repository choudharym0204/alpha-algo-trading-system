from __future__ import annotations

import pytest

from alpha_algo_api.config import Settings, get_settings, reset_settings


def test_settings_fail_closed_defaults() -> None:
    reset_settings()
    settings = get_settings()
    assert settings.live_trading_enabled is False
    assert settings.global_trading_halt is True
    assert settings.default_trading_mode == "PAPER"
    reset_settings()


def test_cors_origins_parsed_from_comma_list() -> None:
    settings = Settings(
        cors_allowed_origins="http://localhost:3000, https://app.example.com"
    )
    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://app.example.com",
    ]


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            secret_key="dev-only-insecure-secret-key-change-me",
        )


def test_live_enabled_while_halt_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(live_trading_enabled=True, global_trading_halt=True)


def test_secret_key_is_placeholder() -> None:
    from alpha_algo_api.security.secret import is_placeholder

    assert is_placeholder("dev-only-insecure-secret-key-change-me") is True
    assert is_placeholder("replace-with-x") is True
    assert is_placeholder(None) is True
    assert is_placeholder("") is True
