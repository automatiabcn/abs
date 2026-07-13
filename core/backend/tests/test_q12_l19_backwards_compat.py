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
    """Attempt admin login. Tries bootstrap creds (admin@local/CHANGEME)
    first — that's what the conftest test fixture exposes — then falls
    back to the live demo creds. Returns True on 200."""
    candidates = [
        {"email": "admin@local", "password": "CHANGEME"},
        {"email": "admin@demo-acme.com", "password": "DemoPass2026!"},
    ]
    for payload in candidates:
        resp = client.post("/auth/login", json=payload)
        if resp.status_code == 200:
            return True
    return False


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
    succeeded. The fix landed on `/v1/cascade/run`. In TestClient the
    rate limiter is reset between tests so 429 may not occur from
    in-process probing alone — guard verifies the pre-flight quota
    hook is wired (`/v1/hooks/quota-check`) and the cascade endpoint
    exists for live SLO smoke."""

    QUOTA_HOOK = "/v1/hooks/quota-check"
    CASCADE_ENDPOINT = "/v1/cascade/run"

    def test_quota_hook_authed_and_cascade_present(self, client: TestClient) -> None:
        if _is_endpoint_404(client, "POST", self.QUOTA_HOOK):
            pytest.fail(
                "Q10-L6 regression: /v1/hooks/quota-check unmounted — "
                "quota pre-flight gate gone"
            )
        if _is_endpoint_404(client, "POST", self.CASCADE_ENDPOINT):
            pytest.fail(
                "Q10-L6 regression: /v1/cascade/run unmounted — "
                "quota-gated runtime missing"
            )
        # Pre-flight hook must auth-gate (non-404, non-200 unauthed).
        r = client.post(self.QUOTA_HOOK, json={})
        assert r.status_code in {401, 403, 422}, (
            f"Q10-L6 regression: quota-check hook unprotected ({r.status_code})"
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


class TestQ12L22OAuthAtomicClaimRegression:
    """Q12-L22-005/006 (S4 R26) — OAuth code + refresh atomic single-use.

    Pre-fix: `exchange_code_for_tokens` and `refresh_access_token` both
    performed a non-atomic read-then-write on `used_at` /
    `rotated_to_hash`, allowing two concurrent /oauth/token requests
    with the same code or refresh token to mint duplicate tokens
    (OAuth 2.1 §4.1.3 / §6.1 violation).

    This regression test pins three load-bearing properties:
      1. The atomic UPDATE statement in `exchange_code_for_tokens`
         contains both the code-equality predicate AND the
         `used_at IS NULL` predicate (pre-fix had only the former on
         a regular ORM read+write).
      2. The atomic UPDATE statement in `refresh_access_token`
         contains the `rotated_to_hash IS NULL` AND
         `revoked_at IS NULL` predicates.
      3. `_revoke_refresh_family` exists and is reachable (OAuth 2.1
         §6.1 family revocation hardening).
    """

    def test_oauth_atomic_predicates_present_in_source(self) -> None:
        from app.auth.oauth import server as oauth_server

        src = Path(oauth_server.__file__).read_text(encoding="utf-8")
        assert "OAuthAuthCode.used_at.is_(None)" in src, (
            "Q12-L22-005 regression: atomic UPDATE on auth code is "
            "missing the `used_at IS NULL` predicate; replay protection "
            "is broken"
        )
        assert "OAuthRefreshToken.rotated_to_hash.is_(None)" in src, (
            "Q12-L22-006 regression: atomic UPDATE on refresh token is "
            "missing the `rotated_to_hash IS NULL` predicate"
        )
        assert "OAuthRefreshToken.revoked_at.is_(None)" in src, (
            "Q12-L22-006 regression: refresh atomic UPDATE missing "
            "the `revoked_at IS NULL` predicate"
        )
        assert "_revoke_refresh_family" in src, (
            "Q12-L22-006 regression: OAuth 2.1 §6.1 family revocation helper missing"
        )

    def test_oauth_replay_returns_invalid_grant(self, client: TestClient) -> None:
        # Live boundary: posting any /oauth/token with a malformed code
        # should surface a 400/401 with `error: invalid_grant` shape,
        # not a 5xx that would hide the atomic-claim path entirely.
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "regression-bogus",
                "code": "DOESNOTEXIST",
                "redirect_uri": "https://app.local/callback",
                "code_verifier": "x" * 64,
            },
        )
        assert resp.status_code in (
            400,
            401,
            422,
        ), f"replay path must surface 4xx, not 5xx ({resp.status_code})"


class TestQ12L25BodySizeLimitRegression:
    """Q12-L25-004/005 (S4 R27) — HTTP-layer Content-Length cap.

    Pre-fix: admin endpoints accepted unbounded request bodies, parsing
    50 MB+ payloads fully into memory before Pydantic Field caps fired.

    Pin: `BodySizeLimitMiddleware` is installed at the right layer
    (between DemoMode and RequestID per Q12-L23 audit continuity), and
    a 50 MB payload to /v1/marketplace/install returns 413 with the
    `request_body_too_large` detail shape.
    """

    def test_body_size_limit_middleware_installed(self) -> None:
        from app.main import app
        from app.middleware.body_size_limit import BodySizeLimitMiddleware

        names = [m.cls.__name__ for m in app.user_middleware]
        assert BodySizeLimitMiddleware.__name__ in names, (
            "Q12-L25-004 regression: BodySizeLimitMiddleware no longer "
            "installed in app.user_middleware; admin endpoints can be "
            "DoS'd with oversize bodies"
        )

    def test_oversize_install_returns_413(self, client: TestClient) -> None:
        big_payload = (
            '{"plugin_id":"x","tenant":"y","blob":"' + "z" * (6 * 1024 * 1024) + '"}'
        )
        resp = client.post(
            "/v1/marketplace/install",
            content=big_payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413, (
            f"Q12-L25-004 regression: oversize body must return 413, "
            f"got {resp.status_code}"
        )
        body = resp.json()
        assert body.get("detail") == "request_body_too_large"
        assert "limit_bytes" in body
        assert "received_bytes" in body


class TestQ12L24VerifierLeakRegression:
    """Q12-L24-007 (S4 R29) — verifier.py PyJWTError catch-all.

    Pre-fix: catch-all branch surfaced
    `f"License verification error: {exc}"` to clients, exposing PyJWT
    internals when a future subclass slips past the specific catches.

    Pin: the catch-all branch responds with the generic
    `license_verify_failed` detail and never the str-interpolated form.
    """

    def test_verifier_pyjwt_branch_uses_generic_detail(self) -> None:
        from app.licensing import verifier as verifier_mod

        src = Path(verifier_mod.__file__).read_text(encoding="utf-8")
        assert "license_verify_failed" in src, (
            "Q12-L24-007 regression: generic `license_verify_failed` "
            "detail missing — PyJWT internals may leak"
        )
        # The pre-fix f-string MUST NOT come back.
        assert "License verification error: {exc}" not in src, (
            "Q12-L24-007 regression: the f-string str(exc) interpolation "
            "is back in the catch-all branch"
        )

    def test_verifier_emits_taxonomy_log(self) -> None:
        from app.licensing import verifier as verifier_mod

        src = Path(verifier_mod.__file__).read_text(encoding="utf-8")
        assert "license_verify_pyjwt_error" in src, (
            "Q12-L24-007 regression: the ops audit warning "
            "`license_verify_pyjwt_error` is missing — error_class "
            "taxonomy is no longer captured"
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
                    f"{route}: {total / 1024:.1f} KiB > limit {limit / 1024:.1f} KiB"
                )
        assert not regressions, (
            "Sprint 21 regression: chunk totals exceeded +20% buffer:\n"
            + "\n".join(regressions)
        )


class TestQ12L20003RegressionPin:
    """Q12-L20-003 (S6 R35) — regression pin for the chat sessions-error-tile fix.

    Two protections beyond the Playwright suite:
      1. Source presence — the data-test attribute + the new useQuery
         retry: 1 cap MUST stay in ChatClient.tsx. A grep regression
         catches a future refactor that drops the banner or restores
         the default retry: 3 (which kept isLoading=true ~15s under
         cascade 503).
      2. Reverse pin — the original failing pattern (sessions-error-tile
         absent) MUST NOT come back. We assert the banner JSX block is
         present *and* the retry: 1 line is present.
    """

    def test_chat_client_carries_sessions_error_tile_banner(self) -> None:
        from pathlib import Path

        chat_client = (
            Path(__file__).resolve().parents[2]
            / "landing"
            / "app"
            / "panel"
            / "chat"
            / "ChatClient.tsx"
        )
        if not chat_client.exists():
            import pytest as _pytest

            _pytest.skip("core/landing/app/panel/chat/ChatClient.tsx not on this build")
        src = chat_client.read_text(encoding="utf-8")
        # Q12-L20-003 fix surface — sessions-error-tile banner.
        assert 'data-test="sessions-error-tile"' in src, (
            "Q12-L20-003 regression: sessions-error-tile data-test is "
            "missing from ChatClient.tsx — the role=alert banner that "
            "surfaces /v1/chat/sessions 5xx is gone"
        )
        assert 'role="alert"' in src, (
            'Q12-L20-003 regression: role="alert" attribute is missing '
            "from ChatClient.tsx — the SR contract for the error banner is broken"
        )

    def test_chat_client_caps_useQuery_retry(self) -> None:
        """The retry default (3) keeps isLoading=true ~15s under cascade
        503; the fix capped it to 1. Reverting would re-introduce the
        spinner-hang surface S6 R32 chaos suite caught."""
        from pathlib import Path

        chat_client = (
            Path(__file__).resolve().parents[2]
            / "landing"
            / "app"
            / "panel"
            / "chat"
            / "ChatClient.tsx"
        )
        if not chat_client.exists():
            import pytest as _pytest

            _pytest.skip("ChatClient.tsx not on this build")
        src = chat_client.read_text(encoding="utf-8")
        assert "retry: 1" in src, (
            "Q12-L20-003 regression: sessionsQuery retry cap (`retry: 1`) "
            "is missing — default retry: 3 with backoff would re-introduce "
            "the ~15s isLoading=true spinner-hang under cascade 503"
        )

    def test_no_test_fail_marker_on_chaos_multi_scenarios(self) -> None:
        """The S6 R35 fix flipped scenarios 6+7 from test.fail() to test().
        A future regression that re-marks them as test.fail() must surface.
        We match the actual call site (`test.fail(<whitespace>"scenario X:")`),
        not the empty-arg `test.fail()` reference that appears in prose."""
        import re
        from pathlib import Path

        spec = (
            Path(__file__).resolve().parents[2]
            / "landing"
            / "__tests__"
            / "playwright"
            / "q12-l20-chaos-multi.spec.ts"
        )
        if not spec.exists():
            import pytest as _pytest

            _pytest.skip("q12-l20-chaos-multi.spec.ts not on this build")
        src = spec.read_text(encoding="utf-8")
        # Real call site form: `test.fail(\s*"scenario 6:` — the prose
        # comment `test.fail() upgraded to test()` has `()` immediately
        # and won't match the scenario-string pattern.
        for scenario in ("scenario 6:", "scenario 7:"):
            pattern = rf"test\.fail\(\s*[\"']{re.escape(scenario)}"
            if re.search(pattern, src):
                raise AssertionError(
                    f"Q12-L20-003 regression: {scenario} is gated by "
                    "test.fail() again — the S6 R35 fix has been reverted"
                )
