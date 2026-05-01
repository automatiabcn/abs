"""Q11 Round 19 / L10 — stress derinleştirme.

Two contracts under test:

  1. Quota gate's rolling-hour deque actually drops entries older than
     1 hour on the next call (Q10-L6-001 documented the design;
     Q11-L19 verifies the implementation).

  2. /v1/chat/completions emits a "thinking" SSE frame before the
     cascade call (Q11-L10-002 fix). Catches a regression where a
     long-running cascade silently blocks the SSE stream past a 30s
     proxy idle timeout.
"""

from __future__ import annotations

import json
import time

import pytest

from app.api import claude_code_hooks as ccx


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(
        settings, "anthropic_mock_mode", "ok", raising=False
    )


class TestQ11L10QuotaRollingWindow:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200
        return client

    def _mint(self, c) -> str:
        r = c.post(
            "/v1/mcp/tokens",
            json={"label": "q11-rolling", "scope": "all", "ttl_days": 1},
        )
        return r.json()["token"]

    def test_rolling_window_drops_entries_older_than_1h(
        self, admin_client
    ):
        """Pre-populate the in-memory deque with 200 fake-old timestamps,
        then make one real risky-tool call. Old entries must drop, count
        must reset to 1 (only the new call), and the response must be
        allow."""
        token = self._mint(admin_client)
        ccx._risky_window.clear()

        # Resolve the test admin's tenant so we plant entries on the
        # right key.
        from app.api.chat import _resolve_tenant
        from app.api.mcp_tokens import verify_token

        payload = verify_token(token)
        tenant = payload["tenant"]

        # 200 timestamps from 2 hours ago — all should be dropped
        # before the new call lands in the bucket.
        old_ts = time.time() - 7200
        for _ in range(200):
            ccx._risky_window[tenant].append(old_ts)
        assert len(ccx._risky_window[tenant]) == 200

        r = admin_client.post(
            "/v1/hooks/quota-check",
            json={"tool_name": "Bash"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        decision = r.json()["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow", (
            "rolling-window did not drop expired entries — counter "
            "stayed at 200 and the gate refused"
        )
        # Bucket size after = 1 (just the now() insertion).
        assert len(ccx._risky_window[tenant]) == 1

    def test_rolling_window_keeps_recent_entries(self, admin_client):
        """Plant 99 entries from 30 minutes ago — those are within the
        1h window. One more risky call lands at count=100 (still allow,
        edge of limit). 101st call denies."""
        token = self._mint(admin_client)
        ccx._risky_window.clear()
        from app.api.mcp_tokens import verify_token

        tenant = verify_token(token)["tenant"]
        recent_ts = time.time() - 1800  # 30 min ago
        for _ in range(99):
            ccx._risky_window[tenant].append(recent_ts)

        r = admin_client.post(
            "/v1/hooks/quota-check",
            json={"tool_name": "Bash"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert (
            r.json()["hookSpecificOutput"]["permissionDecision"]
            == "allow"
        ), "100th call should allow (count=100, limit=100)"

        r2 = admin_client.post(
            "/v1/hooks/quota-check",
            json={"tool_name": "Bash"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert (
            r2.json()["hookSpecificOutput"]["permissionDecision"]
            == "deny"
        ), "101st call should deny (count=101 > 100)"


class TestQ11L10SseThinkingHeartbeat:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200
        return client

    def test_completions_emits_thinking_frame_before_cascade(
        self, admin_client
    ):
        """Q11-L10-002 fix: the SSE stream must yield a 'thinking'
        frame between the session frame and the first text chunk so a
        slow cascade doesn't silently exhaust a proxy idle timeout."""
        with admin_client.stream(
            "POST",
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "ping"}]},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith(
                "text/event-stream"
            )

            frames: list[dict] = []
            for raw in resp.iter_lines():
                if not raw.startswith("data: "):
                    continue
                payload = raw[len("data: "):]
                if payload == "[DONE]":
                    break
                frames.append(json.loads(payload))
                if len(frames) >= 4:  # session, thinking, text, meta
                    break

        types = [f.get("type") for f in frames]
        assert types[0] == "session", types
        assert "thinking" in types, (
            f"no thinking frame between session and text — proxy 30s "
            f"timeout risk reintroduced. Types: {types}"
        )
