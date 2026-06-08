"""External MCP federation — SSRF guard, encrypted CRUD, admin API + flag gate."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings
from app.mcp.external import client as ext_client
from app.mcp.external import service


# ── SSRF guard ──────────────────────────────────────────────────────────────


def test_ssrf_blocks_localhost_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", False, raising=False)
    with pytest.raises(ext_client.ExternalMcpError):
        ext_client._assert_safe_url("http://127.0.0.1:8000/mcp")


def test_ssrf_blocks_private_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", False, raising=False)
    for url in (
        "http://10.0.0.5/mcp",
        "http://192.168.1.10/mcp",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
    ):
        with pytest.raises(ext_client.ExternalMcpError):
            ext_client._assert_safe_url(url)


def test_ssrf_rejects_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    for url in ("file:///etc/passwd", "ftp://x/y", "gopher://x"):
        with pytest.raises(ext_client.ExternalMcpError):
            ext_client._assert_safe_url(url)


def test_ssrf_allows_private_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    ext_client._assert_safe_url("http://127.0.0.1:8000/mcp")  # no raise


def test_ssrf_allows_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", False, raising=False)
    # 8.8.8.8 is public — passes the IP-range gate (no connection is made here).
    ext_client._assert_safe_url("https://8.8.8.8/mcp")


# ── build_headers ───────────────────────────────────────────────────────────


def test_build_headers_shapes() -> None:
    assert ext_client.build_headers("none", "", "") == {}
    assert ext_client.build_headers("bearer", "tok", "") == {
        "Authorization": "Bearer tok"
    }
    assert ext_client.build_headers("header", "v", "X-Key") == {"X-Key": "v"}
    # header auth without a name yields nothing (caller validates upstream).
    assert ext_client.build_headers("header", "v", "") == {}


# ── service CRUD (encrypted, tenant-scoped, no secret leak) ──────────────────


def test_add_stores_ciphertext_not_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    monkeypatch.setattr(
        settings, "provider_key_encryption_key", "unit-master", raising=False
    )
    pub = service.add_server(
        tenant_slug="t-ext",
        name="GitHub MCP",
        url="https://api.example.com/mcp",
        transport="http",
        auth_type="bearer",
        secret="ghp_supersecret",
    )
    # Public dict NEVER carries the secret.
    assert "ghp_supersecret" not in str(pub)
    assert pub["has_auth"] is True
    assert "secret" not in pub and "encrypted_auth" not in pub

    # Row at rest holds ciphertext, not the plaintext token.
    from sqlmodel import Session, select

    from app.db.session import get_engine
    from app.db.tenant_models import ExternalMcpServer

    with Session(get_engine()) as db:
        row = db.exec(
            select(ExternalMcpServer).where(
                ExternalMcpServer.tenant_slug == "t-ext",
                ExternalMcpServer.slug == pub["slug"],
            )
        ).first()
    assert row is not None
    assert "ghp_supersecret" not in row.encrypted_auth
    assert row.encrypted_auth  # something stored


def test_slug_disambiguation(monkeypatch: pytest.MonkeyPatch) -> None:
    # allow_private skips the SSRF DNS probe (reserved .example never resolves);
    # these tests exercise CRUD logic, not connectivity.
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    a = service.add_server(tenant_slug="t-slug", name="Dup", url="https://a.example/mcp")
    b = service.add_server(tenant_slug="t-slug", name="Dup", url="https://b.example/mcp")
    assert a["slug"] != b["slug"]


def test_tenant_isolation_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    service.add_server(tenant_slug="t-iso-1", name="One", url="https://1.example/mcp")
    service.add_server(tenant_slug="t-iso-2", name="Two", url="https://2.example/mcp")
    slugs1 = {s["slug"] for s in service.list_servers("t-iso-1")}
    names2 = {s["name"] for s in service.list_servers("t-iso-2")}
    assert "two" not in slugs1
    assert names2 == {"Two"}


def test_update_and_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    pub = service.add_server(tenant_slug="t-upd", name="Edit", url="https://e.example/mcp")
    slug = pub["slug"]
    upd = service.update_server(tenant_slug="t-upd", slug=slug, enabled=False, name="Edited")
    assert upd is not None and upd["enabled"] is False and upd["name"] == "Edited"
    assert service.remove_server("t-upd", slug) is True
    assert service.get_server("t-upd", slug) is None
    assert service.remove_server("t-upd", slug) is False  # idempotent


def test_add_validates_auth_shape() -> None:
    with pytest.raises(ValueError):
        service.add_server(
            tenant_slug="t-val", name="NoTok", url="https://x.example/mcp",
            auth_type="bearer", secret="",
        )
    with pytest.raises(ValueError):
        service.add_server(
            tenant_slug="t-val", name="NoHdr", url="https://x.example/mcp",
            auth_type="header", secret="v", header_name="",
        )


@pytest.mark.asyncio
async def test_test_connection_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    monkeypatch.setattr(settings, "external_mcp_timeout_seconds", 2.0, raising=False)
    pub = service.add_server(
        tenant_slug="t-err", name="Dead", url="http://127.0.0.1:59999/mcp",
    )
    res = await service.test_connection("t-err", pub["slug"])
    assert res["ok"] is False and "error" in res
    # snapshot persisted as error
    row = service.get_server("t-err", pub["slug"])
    assert row is not None and row["status"] == "error"


# ── admin API + feature flag gate ───────────────────────────────────────────


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_api_404_when_feature_disabled(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_enabled", False, raising=False)
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/v1/admin/external-mcp", headers=h).status_code == 404


def test_api_requires_admin(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_enabled", True, raising=False)
    assert client.get("/v1/admin/external-mcp").status_code in (401, 403)


def test_api_add_list_delete(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_enabled", True, raising=False)
    monkeypatch.setattr(settings, "external_mcp_allow_private", False, raising=False)
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}

    add = client.post(
        "/v1/admin/external-mcp",
        headers=h,
        json={"name": "Public MCP", "url": "https://8.8.8.8/mcp"},
    )
    assert add.status_code == 201, add.text
    slug = add.json()["slug"]

    lst = client.get("/v1/admin/external-mcp", headers=h)
    assert lst.status_code == 200
    assert any(s["slug"] == slug for s in lst.json()["servers"])

    dele = client.delete(f"/v1/admin/external-mcp/{slug}", headers=h)
    assert dele.status_code == 200 and dele.json()["ok"] is True


def test_api_rejects_ssrf_url(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_mcp_enabled", True, raising=False)
    monkeypatch.setattr(settings, "external_mcp_allow_private", False, raising=False)
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post(
        "/v1/admin/external-mcp",
        headers=h,
        json={"name": "Evil", "url": "http://169.254.169.254/latest"},
    )
    assert r.status_code == 422


# ── description sanitisation + response cap ─────────────────────────────────


def test_sanitize_description_strips_control_chars_and_caps() -> None:
    raw = "Hello\x00\x07 world" + "x" * 1000
    out = ext_client.sanitize_description(raw)
    assert "\x00" not in out and "\x07" not in out
    assert "Hello world" in out.replace("xxxx", "")[:20] or out.startswith("Hello")
    assert len(out) <= 500


# ── federation (FastMCP re-expose) ──────────────────────────────────────────


def test_federated_name_sanitizes() -> None:
    from app.mcp.external import federation as fed

    assert fed.federated_name("local-abs", "system_status") == "ext_local_abs__system_status"
    assert fed.federated_name("a b!c", "do/it") == "ext_a_b_c__do_it"


def test_federation_off_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp.external import federation as fed

    monkeypatch.setattr(settings, "external_mcp_federate_to_mcp", False, raising=False)
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    pub = service.add_server(tenant_slug="t-fed-off", name="Off", url="https://x.example/mcp")
    import asyncio

    n = asyncio.run(fed.federate_server("t-fed-off", pub["slug"]))
    assert n == 0


def test_federate_registers_and_unregisters(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp.external import client as cl
    from app.mcp.external import federation as fed
    from app.mcp.server import mcp_server

    monkeypatch.setattr(settings, "external_mcp_federate_to_mcp", True, raising=False)
    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)

    fake = [
        cl.ExternalTool(name="alpha", description="a", input_schema={"type": "object"}),
        cl.ExternalTool(name="beta", description="b", input_schema={"type": "object"}),
    ]

    async def _fake_discover(url, transport, headers=None):
        return fake

    monkeypatch.setattr(cl, "discover_tools", _fake_discover)
    pub = service.add_server(tenant_slug="t-fed", name="Fed", url="https://x.example/mcp")
    slug = pub["slug"]

    import asyncio

    n = asyncio.run(fed.federate_server("t-fed", slug))
    assert n == 2
    tm = mcp_server._tool_manager._tools
    assert fed.federated_name(slug, "alpha") in tm
    assert fed.federated_name(slug, "beta") in tm

    removed = fed.unfederate_server(slug)
    assert removed == 2
    assert fed.federated_name(slug, "alpha") not in tm


def test_call_federated_tenant_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp.external import federation as fed

    monkeypatch.setattr(settings, "external_mcp_allow_private", True, raising=False)
    import asyncio

    # unknown server → not_found, never connects
    res = asyncio.run(fed.call_federated("t-x", "nope", "tool", {}))
    assert res["ok"] is False and res["text"] == "not_found"
