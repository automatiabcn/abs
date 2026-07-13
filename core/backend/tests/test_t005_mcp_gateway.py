"""T-005 — MCP gateway base tests.

Covers JWT validation, Cerbos authorization, and end-to-end happy path
(authorize → token → /v1/projects/{id}). The Cerbos PDP is replaced by
an in-process fake set on `app.state.cerbos_client` so the test does
not require a running PDP.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def _seed_client(client_id: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris="https://app.local/callback",
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()


class _FakeCerbos:
    """In-process stand-in implementing only `check_resources`."""

    def __init__(self, *, allow: bool):
        self.allow = allow
        self.calls: list[tuple[Any, Any]] = []

    def check_resources(self, *, principal, resources):  # noqa: ANN001
        self.calls.append((principal, resources))
        action_set = set()
        for ra in getattr(resources, "resources", []):
            action_set.update(ra.actions)
        entry = SimpleNamespace(is_allowed=lambda action: self.allow)
        return SimpleNamespace(
            results=[entry],
            failed=lambda: False,
            status_code=200,
        )

    def close(self) -> None:  # pragma: no cover — interface compat
        pass


@pytest.fixture(autouse=True)
def _a_real_project():
    """Seed the project these tests read.

    They used to read it from a hardcoded dict inside the endpoint — so the test
    and the fabrication propped each other up, and the endpoint's 404 for a
    customer's actual project was invisible to both. The project is a row now, so
    the test has to put one there."""
    from datetime import datetime, timezone

    from sqlmodel import Session, select

    from app.db.session import get_engine
    from app.db.tenant_models import Project

    with Session(get_engine()) as db:
        exists = db.exec(select(Project).where(Project.slug == "proj-t1-alice")).first()
        if exists is None:
            db.add(
                Project(
                    slug="proj-t1-alice",
                    tenant_slug="tenant-1",
                    name="Alice Project",
                    owner_subject="alice",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()


@pytest.fixture()
def install_fake_cerbos():
    def _install(allow: bool) -> _FakeCerbos:
        fake = _FakeCerbos(allow=allow)
        app.state.cerbos_client = fake
        return fake

    yield _install
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def _issue_token(
    cli: TestClient,
    *,
    client_id: str,
    user_subject: str,
    tenant_id: str,
    roles: list[str],
) -> str:
    verifier = "v" * 64
    auth = cli.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": user_subject,
            "tenant_id": tenant_id,
            "roles": ",".join(roles),
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302, auth.text
    code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]

    tok = cli.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"]


def test_invalid_jwt_returns_401() -> None:
    with TestClient(app) as c:
        r = c.get(
            "/v1/projects/proj-t1-alice",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
    assert r.status_code == 401
    assert "invalid_token" in r.json()["detail"]


def test_missing_authorization_header_returns_401() -> None:
    with TestClient(app) as c:
        r = c.get("/v1/projects/proj-t1-alice")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_authorized_request_returns_200(install_fake_cerbos) -> None:
    cid = f"gw-c1-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake = install_fake_cerbos(allow=True)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.get(
            "/v1/projects/proj-t1-alice",
            headers={
                "Authorization": f"Bearer {token}",
                "X-ABS-Audience": cid,
            },
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "proj-t1-alice"
    assert body["principal"] == "alice"
    assert "served_at" in body
    # The fake PDP saw exactly one query for the read action.
    assert len(fake.calls) == 1
    principal, resources = fake.calls[0]
    assert principal.id == "alice"
    assert principal.attr.get("tenant_id") == "tenant-1"


def test_unauthorized_subject_returns_403(install_fake_cerbos) -> None:
    cid = f"gw-c2-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_fake_cerbos(allow=False)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="carol",
            tenant_id="tenant-2",
            roles=["member"],
        )
        r = c.get(
            "/v1/projects/proj-t1-alice",
            headers={
                "Authorization": f"Bearer {token}",
                "X-ABS-Audience": cid,
            },
        )

    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden"


def test_unknown_project_returns_404(install_fake_cerbos) -> None:
    cid = f"gw-c3-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_fake_cerbos(allow=True)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.get(
            "/v1/projects/does-not-exist",
            headers={
                "Authorization": f"Bearer {token}",
                "X-ABS-Audience": cid,
            },
        )

    assert r.status_code == 404


def test_jwt_carries_tenant_and_roles(install_fake_cerbos) -> None:
    cid = f"gw-c4-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_fake_cerbos(allow=True)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="dan",
            tenant_id="tenant-1",
            roles=["admin", "member"],
        )

    import jwt as _jwt
    from app.auth.oauth.jwks import public_verification_key

    claims = _jwt.decode(
        token,
        public_verification_key(),
        algorithms=["RS256"],
        audience=cid,
        issuer="https://abs.local",
    )
    assert claims["tnt"] == "tenant-1"
    assert set(claims["roles"]) == {"admin", "member"}


def test_authorized_request_latency_under_100ms(install_fake_cerbos) -> None:
    cid = f"gw-c5-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_fake_cerbos(allow=True)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-1",
            roles=["member"],
        )
        # Warm-up
        c.get(
            "/v1/projects/proj-t1-alice",
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
        samples: list[float] = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = c.get(
                "/v1/projects/proj-t1-alice",
                headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
            )
            samples.append((time.perf_counter() - t0) * 1000.0)
            assert r.status_code == 200
    samples.sort()
    p95 = samples[int(0.95 * len(samples))]
    assert p95 < 100.0, f"gateway p95 {p95:.2f}ms exceeds 100ms"
