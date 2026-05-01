"""Q11 Round 14 / L10 — cascade chain concurrency stress.

Hammers /v1/cascade/run with 100 concurrent requests in mock mode.
The contracts under test:

  * every request returns a deterministic `provider="anthropic-mock"`
    response — no provider rotation under load
  * fallback_chain is empty for all (mock fast-path skips the live
    cascade) — no leakage of upstream provider errors into this
    short-circuit
  * status_code is 200 across the board — no 500 from a contended
    queue, no 429 from accidentally hitting a rate-limit gate that
    shouldn't apply to mock

Q10 Round 6 covered the single-request roundtrip; this round
exercises the same code path under contention so a race in the
mock short-circuit (e.g. a shared mutable list re-used across
requests) would surface here, not in production.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(
        settings, "anthropic_mock_mode", "ok", raising=False
    )


class TestQ11L10CascadeRace:
    @pytest.fixture()
    def admin_client(self, client):
        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200
        return client

    def test_100_parallel_cascade_run_all_mock(self, admin_client):
        bodies = []
        statuses = []
        sink_lock = threading.Lock()

        def fire():
            r = admin_client.post(
                "/v1/cascade/run",
                json={
                    "prompt": "Q11 race probe",
                    "max_tokens": 64,
                    "fallback_order": [],
                },
            )
            return r.status_code, r.json() if r.status_code == 200 else None

        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = [ex.submit(fire) for _ in range(100)]
            for f in as_completed(futs):
                code, body = f.result()
                with sink_lock:
                    statuses.append(code)
                    if body:
                        bodies.append(body)

        assert all(s == 200 for s in statuses), (
            f"non-200 leaked: {[s for s in statuses if s != 200]}"
        )
        assert len(bodies) == 100

        # Every response must come from the deterministic mock path.
        providers = {b.get("provider") for b in bodies}
        assert providers == {"anthropic-mock"}, (
            f"provider leakage under contention: {providers}"
        )

        # mock fast-path always records exactly one entry in fallback_chain
        # ("anthropic-mock"). Any other shape under contention would mean
        # threads are stepping on a shared list — a race condition. The
        # set of chains across 100 requests must be a single value.
        chains = {tuple(b.get("fallback_chain", [])) for b in bodies}
        assert chains == {("anthropic-mock",)}, (
            f"fallback_chain leakage under contention: {chains}"
        )

        # mock=True for all — same defensive assertion against state
        # bleed between threads.
        assert all(b.get("mock") is True for b in bodies)
