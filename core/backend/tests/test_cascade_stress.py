"""quota gate stress + concurrency.

Hammers /v1/hooks/quota-check with 200 concurrent requests against a
single tenant. RISKY_HOURLY_LIMIT is 100, so the contract is:
  * exactly 100 requests must return permissionDecision="allow"
  * the remaining 100 must return permissionDecision="deny"

If the lock around `_risky_window` (`threading.Lock` over a deque)
isn't atomic the counts will drift — extra allows mean lost updates,
extra denies mean phantom counts. Either way the test catches the
regression before it ships.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.api import claude_code_hooks as ccx


class TestQuotaGateStress:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200, r.text
        return client

    def _mint_token(self, c) -> str:
        r = c.post(
            "/v1/mcp/tokens",
            json={"label": "q11-stress", "scope": "all", "ttl_days": 1},
        )
        assert r.status_code == 201, r.text
        return r.json()["token"]

    def test_parallel_risky_quota_check_splits_100_100(self, admin_client):
        # Reset the in-process counter so the stress test starts clean
        # regardless of test ordering inside the suite.
        ccx._risky_window.clear()

        token = self._mint_token(admin_client)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"tool_name": "Bash"}

        allows = 0
        denies = 0
        other: list[str] = []
        count_lock = threading.Lock()

        def fire_one():
            resp = admin_client.post(
                "/v1/hooks/quota-check", json=payload, headers=headers
            )
            assert resp.status_code == 200, resp.text
            decision = resp.json()["hookSpecificOutput"]["permissionDecision"]
            return decision

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(fire_one) for _ in range(200)]
            for fut in as_completed(futures):
                decision = fut.result()
                with count_lock:
                    if decision == "allow":
                        allows += 1
                    elif decision == "deny":
                        denies += 1
                    else:
                        other.append(decision)

        assert other == [], f"unexpected decisions: {other}"
        assert allows == 100, f"expected 100 allow, got {allows} (denies={denies})"
        assert denies == 100, f"expected 100 deny, got {denies} (allows={allows})"

    def test_non_risky_tool_unbounded(self, admin_client):
        ccx._risky_window.clear()

        token = self._mint_token(admin_client)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"tool_name": "Read"}

        # 300 reads (above the risky limit) — all must allow because Read
        # is non-risky. Confirms the gate doesn't accidentally apply to
        # non-risky tools under load.
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [
                ex.submit(
                    admin_client.post,
                    "/v1/hooks/quota-check",
                    json=payload,
                    headers=headers,
                )
                for _ in range(300)
            ]
            for fut in as_completed(futures):
                r = fut.result()
                assert r.status_code == 200
                assert r.json()["hookSpecificOutput"]["permissionDecision"] == "allow"
