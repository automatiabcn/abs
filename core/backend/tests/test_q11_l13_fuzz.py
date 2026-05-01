"""Q11 Round 2 / L13 — fuzz / property-based input testing.

Hammers /v1/chat/completions with malformed and boundary-condition
payloads. The contract under test:

  * 4xx for invalid input (graceful pydantic validation)
  * never 500 / connection drop / panic
  * exact-boundary lengths still validate cleanly
  * dangerous content (null bytes, SQLi, control chars) get
    escaped/persisted without code-execution

Existing happy-path tests cover messages_required + last_message_must_be_user;
these add the malicious-input surface.
"""

from __future__ import annotations

import pytest


class TestQ11L13ChatCompletionsFuzz:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200
        return client

    @pytest.fixture(autouse=True)
    def _mock_mode(self, monkeypatch):
        monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
        from app.config import settings

        monkeypatch.setattr(
            settings, "anthropic_mock_mode", "ok", raising=False
        )

    # ─── 1. Boundary lengths ────────────────────────────────────────────

    def test_content_exact_max_length_accepted(self, admin_client):
        """Q11-L13-001: ChatMessageIn.content max_length now mirrors
        CascadeRequest.prompt's 8000-char ceiling — boundary must pass."""
        content = "a" * 8000
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": content}]},
        )
        assert r.status_code == 200, r.text

    def test_content_over_max_length_rejected_422(self, admin_client):
        """Q11-L13-001: anything over 8000 must 422 at pydantic — never
        500 on the cascade ValidationError fallthrough."""
        content = "a" * 8001
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": content}]},
        )
        assert r.status_code == 422
        assert any(
            "content" in str(err.get("loc", []))
            for err in r.json()["detail"]
        )
        # Old upper bound should also still 422, not 500.
        r2 = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "a" * 16385}]},
        )
        assert r2.status_code == 422

    def test_content_empty_string_rejected_422(self, admin_client):
        """Q11-L13-002: content min_length=1 stops the cascade-layer
        ValidationError that previously 500'd on empty input."""
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": ""}]},
        )
        assert r.status_code == 422
        assert any(
            "content" in str(err.get("loc", []))
            for err in r.json()["detail"]
        )

    # ─── 2. Dangerous payloads (no code-exec, no crash) ─────────────────

    def test_null_byte_in_content_handled(self, admin_client):
        r = admin_client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "before\x00after"}
                ]
            },
        )
        # Null bytes commonly break SQLite TEXT bindings → 500. The
        # contract is pydantic clean OR explicit 4xx, never 500.
        assert r.status_code < 500, r.text

    def test_sqli_pattern_in_content_persisted_inert(self, admin_client):
        payload = "'; DROP TABLE chat_messages; --"
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": payload}]},
        )
        assert r.status_code == 200, r.text
        # Subsequent listing must still succeed → table not dropped.
        sessions = admin_client.get("/v1/chat/sessions")
        assert sessions.status_code == 200

    def test_unicode_emoji_rtl_combining_marks(self, admin_client):
        payload = "🚀 مرحبا é ‮RTL_OVERRIDE"
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": payload}]},
        )
        assert r.status_code == 200, r.text

    def test_invalid_role_rejected_422(self, admin_client):
        r = admin_client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {"role": "evil_admin", "content": "hi"}
                ]
            },
        )
        assert r.status_code == 422
        assert any(
            "role" in str(err.get("loc", []))
            for err in r.json()["detail"]
        )

    def test_messages_array_extra_keys_ignored(self, admin_client):
        """Pydantic should drop unknown keys without 500."""
        r = admin_client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "ok",
                        "__proto__": {"polluted": True},
                        "constructor": "Function",
                    }
                ]
            },
        )
        assert r.status_code == 200, r.text

    # ─── 3. Structural malformations ────────────────────────────────────

    def test_messages_missing_field_422(self, admin_client):
        r = admin_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user"}]},  # no content
        )
        assert r.status_code == 422

    def test_session_id_negative_rejected_or_404(self, admin_client):
        r = admin_client.post(
            "/v1/chat/completions",
            json={
                "session_id": -1,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        # Either 422 (validation) or 404 (session_not_found) — both
        # acceptable, neither is 500.
        assert r.status_code in {404, 422}

    def test_extremely_deep_messages_array(self, admin_client):
        """100 messages — backend should accept (panel sends multi-turn)."""
        msgs = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
            for i in range(99)
        ]
        msgs.append({"role": "user", "content": "final"})
        r = admin_client.post(
            "/v1/chat/completions", json={"messages": msgs}
        )
        assert r.status_code == 200, r.text
