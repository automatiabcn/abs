"""004b — 7 geri getirilen widget'ın HTML + stub endpoint parity testleri."""

from __future__ import annotations

# 004 8 widget + 004b 7 widget = 15 widget. Tümünün ID'leri HTML'de bulunmalı.
ALL_WIDGET_IDS = [
    # --- 004 (8 widget) ---
    "brain-iframe",
    "cs-provider-dots",
    "cs-log",
    "spark-deleg",
    "spark-gpu",
    "spark-cache",
    "judge-summary",
    "judge-body",
    "workflow-card",
    "wf-detail-summary",
    "wf-detail-list",
    "cs-cohere-count",
    "cs-cohere-fill",
    "cohere-alert-banner",
    "feat-grid",
    "feat-trend-list",
    "feat-summary",
    "cs-budget-usd",
    "v8-budget-stat",
    "deleg-budget",
    # --- 004b (7 widget) ---
    # Symbol Explorer
    "sym-explorer-summary",
    "sym-explorer-input",
    "sym-explorer-btn",
    "sym-explorer-results",
    # Quota Radar
    "quota-radar-day",
    "quota-radar-grid",
    # Anchor Nav
    "anchor-nav",
    # Notification Bell
    "notif-bell",
    "notif-panel",
    "notif-list",
    "notif-badge",
    "notif-clear",
    "notif-close",
    # Theme Toggle
    "theme-toggle",
    "theme-icon",
    # Disagreement Panel
    "disagree-summary",
    "disagree-body",
    # Vital Signs
    "vital-strip",
    "vital-overall-dot",
    "vital-overall-label",
    "vital-overall-sub",
    "vital-dots",
    "vital-updated",
]


def _login(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200


def test_panel_has_all_15_widgets(client):
    _login(client)
    body = client.get("/panel").text
    missing = [wid for wid in ALL_WIDGET_IDS if f'id="{wid}"' not in body]
    assert not missing, f"Eksik widget ID'leri: {missing}"


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
    assert "008-ask-disagree" in body["note"]


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
