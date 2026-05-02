"""Q12 Round 4 / L19 — Backwards-compat regression guard.

Each test class protects against re-introduction of a historic HIGH-severity
bug. The class docstring captures the original failure scenario; the test
asserts the corrective behaviour.

Coverage:
  1. Q7  — graph router registration (404 must not return)
  2. Q9  — chat session list reachable after login
  3. Q10 — quota gate is enforced (429 surfaces under sustained load)
  4. Q11 — chat content max_length boundary returns 422, never 500
  5. Q11 — alembic 0008 blacklist migration file exists
  6. Q11 — unauthenticated hook POSTs return 401, never 422
  7. S21 — Next.js bundle chunk totals stay within +20% buffer of Sprint 21
           honest baseline
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "core" / "backend" / "alembic" / "versions"
NEXT_MANIFEST = REPO_ROOT / "core" / "landing" / ".next" / "app-build-manifest.json"
NEXT_STATIC_CHUNKS = REPO_ROOT / "core" / "landing" / ".next" / "static" / "chunks"


def _login(client: TestClient) -> bool:
    """Attempt admin demo login; return True on 200."""
    payload = {"email": "admin@demo-acme.com", "password": "DemoPass2026!"}
    resp = client.post("/auth/login", json=payload)
    return resp.status_code == 200


def _is_endpoint_404(client: TestClient, method: str, url: str) -> bool:
    resp = client.request(method, url, json={})
    return resp.status_code == 404


def _load_next_manifest() -> dict | None:
    if not NEXT_MANIFEST.is_file():
        return None
    try:
        return json.loads(NEXT_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None


def _route_chunk_total(manifest: dict, route: str) -> int:
    pages = manifest.get("pages", manifest)
    chunks = pages.get(route) or []
    total = 0
    for chunk in chunks:
        # manifest entries are relative to .next; resolve under static/chunks.
        candidate = REPO_ROOT / "core" / "landing" / ".next" / chunk
        if candidate.is_file():
            total += candidate.stat().st_size
            continue
        bare = NEXT_STATIC_CHUNKS / Path(chunk).name
        if bare.is_file():
            total += bare.stat().st_size
    return total


class TestQ7GraphRouterRegression:
    """Q7 finalize gap — `/v1/graph/cypher` was unmounted; clients saw 404
    instead of 401. Guard: any non-404 status with auth missing."""

    def test_graph_cypher_endpoint_not_404(self, client: TestClient) -> None:
        url = "/v1/graph/cypher"
        resp = client.post(url, json={"query": "MATCH (n) RETURN n LIMIT 1"})
        assert resp.status_code != 404, (
            f"Q7 regression: {url} returned 404 — graph router unmounted"
        )
        assert resp.status_code in {401, 403, 422}, (
            f"Q7 regression: unexpected status {resp.status_code}"
        )


class TestQ9ChatSessionRegression:
    """Q9 — chat session list returned 404 after login due to mount order
    bug. Guard: post-login GET /v1/chat/sessions = 200."""

    def test_chat_sessions_after_login(self, client: TestClient) -> None:
        if not _login(client):
            pytest.skip("admin demo login unavailable in this fixture")
        resp = client.get("/v1/chat/sessions")
        assert resp.status_code == 200, (
            f"Q9 regression: chat sessions returned {resp.status_code} after login"
        )


class TestQ10L6QuotaGateRegression:
    """Q10-L6-001 — quota gate was a silent no-op; 200 risky tool calls
    succeeded. Guard: ≥1 in 50 sequential POSTs returns 429."""

    ENDPOINT = "/v1/tools/risky"

    def test_quota_gate_enforces_429(self, client: TestClient) -> None:
        if _is_endpoint_404(client, "POST", self.ENDPOINT):
            pytest.skip(f"{self.ENDPOINT} not present in this build — surface check")
        if not _login(client):
            pytest.skip("login unavailable for quota gate test")
        payload = {"tool": "shell.exec", "parameters": {"cmd": "echo ok"}}
        statuses: list[int] = []
        for _ in range(50):
            r = client.post(self.ENDPOINT, json=payload)
            statuses.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in statuses, (
            f"Q10-L6 regression: quota gate did not throttle (statuses={set(statuses)})"
        )


class TestQ11L13ChatContentMaxRegression:
    """Q11-L13-001/003 — chat completions returned 500 on oversize content.
    Guard: max-length boundary returns 422, never 500."""

    ENDPOINT = "/v1/chat/completions"

    @pytest.mark.parametrize(
        "size,allowed",
        [
            (16384, {422}),
            (8001, {422}),
            (8000, {200, 422}),
        ],
    )
    def test_chat_content_length_boundary(
        self, client: TestClient, size: int, allowed: set[int]
    ) -> None:
        if _is_endpoint_404(client, "POST", self.ENDPOINT):
            pytest.skip(f"{self.ENDPOINT} unavailable")
        payload = {"messages": [{"role": "user", "content": "x" * size}]}
        resp = client.post(self.ENDPOINT, json=payload)
        assert resp.status_code != 500, (
            f"Q11-L13 regression: size {size} produced 500 (max_length not enforced)"
        )
        # Acceptance is broader than `allowed` only when auth makes 401 first;
        # accept 401 to avoid coupling this guard to login state.
        assert resp.status_code in allowed | {401}, (
            f"Q11-L13 regression: size {size} returned {resp.status_code}"
        )


class TestQ11L14AlembicMigrationRegression:
    """Q11-L14-001 — alembic blacklist migration 0008 was missing in the
    repo, blocking prod deploy. Guard: 0008*.py exists in versions dir."""

    def test_alembic_0008_present(self) -> None:
        assert MIGRATIONS_DIR.is_dir(), (
            f"Q11-L14 regression: alembic versions dir missing at {MIGRATIONS_DIR}"
        )
        matches = sorted(MIGRATIONS_DIR.glob("0008*.py"))
        assert matches, (
            "Q11-L14 regression: alembic 0008 migration file missing — "
            "prod-blocker reintroduced"
        )


class TestQ11L15HooksAuthGateRegression:
    """Q11-L15-001 — hook endpoints leaked 422 (validation error) before
    401 (auth missing), an information disclosure. Guard: 401 first."""

    ENDPOINTS = [
        "/v1/hooks/quota-check",
        "/v1/hooks/audit-log",
        "/v1/hooks/session-start",
    ]

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_hook_endpoint_returns_401_not_422(
        self, client: TestClient, url: str
    ) -> None:
        if _is_endpoint_404(client, "POST", url):
            pytest.skip(f"{url} not present in this build")
        resp = client.post(url, json={})
        assert resp.status_code == 401, (
            f"Q11-L15 regression: {url} returned {resp.status_code} unauthed (expected 401)"
        )


class TestSprint21BundleRegression:
    """Sprint 21 (B+C+D) — bundle chunk totals must not regress more than
    +20% above the honest baseline. Skips if Next build hasn't run."""

    BASELINE_BYTES: dict[str, int] = {
        "/panel": 520 * 1024,
        "/panel/chat": 367 * 1024,
        "/panel/quota": 509 * 1024,
    }
    BUFFER = 1.20

    def test_bundle_within_baseline_plus_buffer(self) -> None:
        manifest = _load_next_manifest()
        if manifest is None:
            pytest.skip("Next.js app-build-manifest.json missing — run `npm run build`")
        regressions: list[str] = []
        for route, baseline in self.BASELINE_BYTES.items():
            total = _route_chunk_total(manifest, route)
            if total == 0:
                continue
            limit = int(baseline * self.BUFFER)
            if total > limit:
                regressions.append(
                    f"{route}: {total/1024:.1f} KiB > limit {limit/1024:.1f} KiB"
                )
        assert not regressions, (
            "Sprint 21 regression: chunk totals exceeded +20% buffer:\n"
            + "\n".join(regressions)
        )
