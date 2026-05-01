"""T-058 — X-ABS-Audience enforcement middleware tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.audience import AudienceEnforcerMiddleware


def _build_app(*, enforce: bool, audience: str = "abs-mcp") -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        AudienceEnforcerMiddleware,
        expected_audience=audience,
        enforce=enforce,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/projects")
    def projects() -> dict[str, list[str]]:
        return {"items": []}

    return app


def test_enforce_disabled_lets_everything_through() -> None:
    client = TestClient(_build_app(enforce=False))
    assert client.get("/v1/projects").status_code == 200


def test_enforce_skips_unprotected_paths() -> None:
    client = TestClient(_build_app(enforce=True))
    assert client.get("/healthz").status_code == 200


def test_enforce_blocks_v1_without_header() -> None:
    client = TestClient(_build_app(enforce=True))
    r = client.get("/v1/projects")
    assert r.status_code == 400
    body = r.json()
    assert body["detail"] == "missing or invalid X-ABS-Audience header"
    assert body["expected"] == "abs-mcp"


def test_enforce_blocks_v1_with_wrong_audience() -> None:
    client = TestClient(_build_app(enforce=True))
    r = client.get("/v1/projects", headers={"X-ABS-Audience": "wrong"})
    assert r.status_code == 400


def test_enforce_blocks_v1_without_authorization() -> None:
    client = TestClient(_build_app(enforce=True))
    r = client.get("/v1/projects", headers={"X-ABS-Audience": "abs-mcp"})
    assert r.status_code == 401
    assert r.json()["detail"] == "missing authorization"


def test_enforce_blocks_v1_with_invalid_token() -> None:
    client = TestClient(_build_app(enforce=True))
    r = client.get(
        "/v1/projects",
        headers={
            "X-ABS-Audience": "abs-mcp",
            "Authorization": "Bearer not.a.real.jwt",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid token or audience mismatch"


def test_install_no_op_when_disabled() -> None:
    from app.middleware.audience import install_audience_enforcer

    class _S:
        audience_enforce = False
        audience_value = "abs-mcp"

    app = FastAPI()

    @app.get("/v1/echo")
    def echo() -> dict[str, str]:
        return {"hi": "ok"}

    install_audience_enforcer(app, _S())
    client = TestClient(app)
    # No middleware was added → unprotected.
    assert client.get("/v1/echo").status_code == 200


def test_install_enables_when_settings_true() -> None:
    from app.middleware.audience import install_audience_enforcer

    class _S:
        audience_enforce = True
        audience_value = "abs-mcp"

    app = FastAPI()

    @app.get("/v1/echo")
    def echo() -> dict[str, str]:
        return {"hi": "ok"}

    install_audience_enforcer(app, _S())
    client = TestClient(app)
    # Enforced → no header → 400.
    assert client.get("/v1/echo").status_code == 400
