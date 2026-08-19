"""API application package for the Alpha Algo Trading System."""

__all__ = ["create_app"]


def __getattr__(name: str):
    # Lazy re-export so that importing this package (or a submodule like
    # ``alpha_algo_api.config``) does not eagerly build the full FastAPI app.
    if name == "create_app":
        from alpha_algo_api.main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
