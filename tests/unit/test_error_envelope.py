from __future__ import annotations

from fastapi.testclient import TestClient

from alpha_algo_api import create_app


def test_unhandled_exception_returns_structured_envelope() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/boom",
        headers={"origin": "http://localhost:3000"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error."
    assert body["error"]["request_id"]
    assert response.headers["x-request-id"]
    # Starlette routes the generic Exception handler through the outermost
    # ServerErrorMiddleware (above CORS), so 500s intentionally omit CORS
    # headers. This is the conservative default: cross-origin clients cannot
    # read 500 response bodies.


def test_validation_error_does_not_echo_raw_input() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "x@x.com", "password": 12345},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    for error in body["error"]["details"]["errors"]:
        assert "input" not in error
        assert "ctx" not in error
        assert set(error.keys()) <= {"type", "loc", "msg"}
