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
    """real implementation: unknown symbol → status='not_found'."""
    _login(client)
    r = client.get("/api/symbol-graph/neighbors?name=ask_groq")
    assert r.status_code == 200
    body = r.json()
    # when DB not yet indexed returns 'not_found'; when indexed returns 'ok'
    assert body["status"] in {"not_found", "ok"}
    assert (
        body.get("name") == "ask_groq" or body.get("root", {}).get("name") == "ask_groq"
    )


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


def test_disagreement_before_anything_was_asked(client):
    from app.disagreement import detector

    detector._last.clear()  # the empty state is the point; don't inherit a run
    _login(client)
    r = client.get("/api/disagreement/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "empty"
    assert body["models"] == []
    assert body["consensus_score"] is None
    # An empty widget with no explanation cannot be told apart from a broken
    # one, so the empty state says which of the two it is.
    assert "asked for yet" in body["note"]


def test_disagreement_shows_the_run_that_happened(client):
    """It used to return a fixed empty payload for ever. A real run has to
    reach the dashboard — and the question must not travel with it."""
    from app.disagreement import detector

    detector._last["default"] = {
        "status": "ok",
        "asked": ["groq", "cerebras"],
        "models": ["groq", "cerebras"],
        "similarity_matrix": [[1.0, 0.2], [0.2, 1.0]],
        "consensus_score": 0.2,
        "consensus_level": "low",
        "similarity_basis": "jaccard",
        "note": "Agreement measured by word overlap.",
        "last_call_at": "2026-08-02T10:00:00+00:00",
    }
    try:
        _login(client)
        body = client.get("/api/disagreement/latest").json()
        assert body["status"] == "ok"
        assert body["consensus_score"] == 0.2
        assert body["models"] == ["groq", "cerebras"]
        assert body["last_call_at"].startswith("2026-08-02")
        assert "responses" not in body, (
            "somebody's question and its answers do not belong on an "
            "operator's dashboard"
        )
    finally:
        detector._last.pop("default", None)


def test_widget_endpoints_require_auth(client):
    for path in (
        "/api/symbol-graph/neighbors?name=x",
        "/api/quota-status",
        "/api/disagreement/latest",
    ):
        r = client.get(path)
        assert r.status_code == 401, f"{path}: beklenen 401, alınan {r.status_code}"


def test_symbol_graph_validates_name_length(client):
    """name min_length=1, max_length=256."""
    _login(client)
    r = client.get("/api/symbol-graph/neighbors?name=")
    assert r.status_code == 422
    # above 256 → 422
    r = client.get("/api/symbol-graph/neighbors?name=" + ("x" * 300))
    assert r.status_code == 422
