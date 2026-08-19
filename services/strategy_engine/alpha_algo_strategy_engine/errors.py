"""Strategy runtime exception hierarchy."""

from __future__ import annotations


class StrategyRuntimeError(Exception):
    """Base for all strategy-runtime errors."""


class RegistryError(StrategyRuntimeError):
    """Registry lifecycle / identity errors."""


class DuplicateRegistrationError(RegistryError):
    """Raised when registering an already-registered strategy identity."""


class StrategyNotFoundError(RegistryError):
    """Raised when a strategy identity is not registered."""


class LifecycleError(StrategyRuntimeError):
    """Illegal or repeated lifecycle transition."""


class ConfigValidationError(StrategyRuntimeError):
    """Invalid or un-hashable strategy configuration."""


class SignalValidationError(StrategyRuntimeError):
    """A strategy emitted an invalid or untraceable signal."""


class TradingModeError(StrategyRuntimeError):
    """Raised when an unsupported trading mode (LIVE) is requested."""
