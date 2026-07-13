"""004b widget endpoints — survives the Brief 4 panel deprecation.

The ``test_panel_has_all_15_widgets`` HTML-ID assertion was removed
because `/panel` is now a 308 redirect to `/admin` (Next.js owns the
widget rendering). The widget *backend* endpoints remain — the Next.js
admin proxies them — so the API parity tests below stay in force.
"""

from __future__ import annotations


def _login(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200


def test_symbol_graph_stub_reachable(client):
    """016 — gerçek implementation: bilinmeyen sembol → status='not_found'."""
    _login(client)
    r = client.get("/api/symbol-graph/neighbors?name=ask_groq")
    assert r.status_code == 200
    body = r.json()
    # DB henüz indexlenmediğinde 'not_found' döner; indexlenmişse 'ok'
    assert body["status"] in {"not_found", "ok"}
    assert body.get("name") == "ask_groq" or body.get("root", {}).get("name") == "ask_groq"


def test_quota_status_stub_reachable(client):
    _login(client)
    r = client.get("/api/quota-status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "empty"
    providers = body["providers"]
    for p in ("anthropic", "groq", "cerebras", "gemini", "cloudflare", "cohere"):
        assert p in providers, f"provider eksik: {p}"
    assert providers["cohere"]["limit"] == 1000


def test_disagreement_stub_reachable(client):
    _login(client)
    r = client.get("/api/disagreement/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "empty"
    assert body["models"] == []
    assert body["consensus_score"] is None
    # The note has to say the feature is not wired up yet — an empty widget with
    # no explanation reads as a broken one.
    assert "not wired up" in body["note"]


def test_widget_endpoints_require_auth(client):
    for path in (
        "/api/symbol-graph/neighbors?name=x",
        "/api/quota-status",
        "/api/disagreement/latest",
    ):
        r = client.get(path)
        assert r.status_code == 401, f"{path}: beklenen 401, alınan {r.status_code}"


def test_symbol_graph_validates_name_length(client):
    """016 — name min_length=1, max_length=256."""
    _login(client)
    r = client.get("/api/symbol-graph/neighbors?name=")
    assert r.status_code == 422
    # 256 üstü → 422
    r = client.get("/api/symbol-graph/neighbors?name=" + ("x" * 300))
    assert r.status_code == 422
