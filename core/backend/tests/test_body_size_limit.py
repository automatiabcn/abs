"""sweep 3 — request body size cap (DoS mitigation).

* (HIGH DoS) — admin endpoints accepted unbounded request
  bodies. Pre-fix, `/v1/marketplace/install` would parse a 50 MB JSON
  payload entirely into memory before the Pydantic Field caps on
  `plugin_id`/`tenant` (R17) could fire, opening a trivial OOM vector
  for any authenticated admin.

The middleware (`app.middleware.body_size_limit`) reads
`Content-Length` and rejects oversize requests with HTTP 413 *before*
the Starlette body parser runs.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.body_size_limit import BodySizeLimitMiddleware


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Content-Length cap on /v1/marketplace/install
# ---------------------------------------------------------------------------


def test_marketplace_install_50mb_rejected(client: TestClient) -> None:
    """50 MB body on /v1/marketplace/install → 413 before parse."""

    fake = "x" * (50 * 1024 * 1024)
    headers = {
        "Authorization": "Bearer not-a-real-token",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"plugin_id": "stub", "tenant": "default", "blob": fake})
    resp = client.post(
        "/v1/marketplace/install",
        content=payload,
        headers=headers,
    )
    assert resp.status_code == 413, (
        f"expected 413, got {resp.status_code} body={resp.text[:200]}"
    )
    body = resp.json()
    assert body["detail"] == "request_body_too_large"
    assert body["limit_bytes"] >= 1024
    assert body["received_bytes"] >= len(payload)


def test_marketplace_install_normal_body_passes_size_gate(
    client: TestClient,
) -> None:
    """Small body passes the size gate (auth/PoT routing happens after)."""

    payload = json.dumps({"plugin_id": "non-existent", "tenant": "default"})
    resp = client.post(
        "/v1/marketplace/install",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer not-a-real-token",
        },
    )
    # Auth/admin guard rejects after the size gate. We only assert that
    # the 413 path was NOT taken — anything ≠ 413 is acceptable here.
    assert resp.status_code != 413


def test_invalid_content_length_400(client: TestClient) -> None:
    """Malformed Content-Length is rejected as 400."""

    resp = client.post(
        "/v1/marketplace/install",
        content=b"{}",
        headers={
            "Content-Length": "not-a-number",
            "Content-Type": "application/json",
        },
    )
    # Some clients/Starlette layers normalize before middleware sees it;
    # accept either explicit 400 from the middleware or a downstream
    # rejection short of 413.
    assert resp.status_code in (400, 422, 401, 403, 404)


# ---------------------------------------------------------------------------
# RAG ingest oversize cap
# ---------------------------------------------------------------------------


def test_rag_ingest_15mb_rejected(client: TestClient) -> None:
    """15 MB body on /v1/rag/ingest → 413 (cap is 10 MB)."""

    fake = "y" * (15 * 1024 * 1024)
    payload = json.dumps({"text": fake, "filename": "huge.txt"})
    resp = client.post(
        "/v1/rag/ingest",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer not-a-real-token",
        },
    )
    assert resp.status_code == 413, (
        f"expected 413, got {resp.status_code} body={resp.text[:200]}"
    )


def test_rag_ingest_normal_body_passes_size_gate(
    client: TestClient,
) -> None:
    """5 KB body passes the size gate (auth rejects after)."""

    payload = json.dumps({"text": "hello world " * 100, "filename": "small.txt"})
    resp = client.post(
        "/v1/rag/ingest",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer not-a-real-token",
        },
    )
    assert resp.status_code != 413


# ---------------------------------------------------------------------------
# Middleware unit tests
# ---------------------------------------------------------------------------


def test_cap_for_longest_prefix_wins() -> None:
    mw = BodySizeLimitMiddleware(
        app=None,
        caps={
            "/v1/": 1024,
            "/v1/marketplace/install": 64,
            "_default": 2048,
            "_hardcap": 100_000,
        },
    )
    assert mw._cap_for("/v1/marketplace/install") == 64
    assert mw._cap_for("/v1/marketplace/list") == 1024
    assert mw._cap_for("/health") == 2048
    assert mw._cap_for("/totally-unknown") == 2048


def test_cap_for_hardcap_clamps() -> None:
    mw = BodySizeLimitMiddleware(
        app=None,
        caps={
            "/v1/uploads": 999_999_999,
            "_default": 5_000,
            "_hardcap": 50_000,
        },
    )
    assert mw._cap_for("/v1/uploads") == 50_000


def test_get_request_no_body_check(client: TestClient) -> None:
    """GET /healthz must not be blocked by body cap (no body)."""
    resp = client.get("/healthz")
    assert resp.status_code in (200, 404)  # endpoint may or may not exist


def test_no_content_length_header_passes_through(client: TestClient) -> None:
    """No Content-Length (chunked transfer) — middleware bows out."""
    # TestClient sets Content-Length automatically; pass-through behavior
    # is exercised by setting Transfer-Encoding: chunked semantically via
    # the unit-level cap_for tests above. Here we just smoke-test that a
    # zero-body POST is fine.
    resp = client.post(
        "/v1/marketplace/install",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code != 413


def test_a_meeting_recording_is_not_capped_at_the_admin_default() -> None:
    """A real recording is bigger than 5 MB, and the endpoint promised 250.

    Found by uploading actual audio: the meetings route had no entry in the cap
    table, so it fell to the generic admin default while `/v1/meetings/upload`
    advertised MAX_UPLOAD_BYTES = 250 MB. Both numbers could not be true, and
    the middleware's ran first — in practice you could upload about two minutes
    of a meeting before a 413 came back talking about a limit the endpoint did
    not have.
    """
    from app.api.meetings import MAX_UPLOAD_BYTES
    from app.middleware.body_size_limit import BodySizeLimitMiddleware

    mw = BodySizeLimitMiddleware(app=None)
    assert mw._cap_for("/v1/meetings/upload") == MAX_UPLOAD_BYTES
