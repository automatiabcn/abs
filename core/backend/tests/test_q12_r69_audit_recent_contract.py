"""Q12 R69 (S8) — /v1/admin/audit/recent contract + edge-case deep.

R64 migrated `/admin/audit` to a server-side split-shell that fetches
`/v1/admin/audit/recent?limit=200` with the caller's session cookie
forwarded. The endpoint is now on the SSR critical path: a regression
in the response shape, source filter behaviour, sort order, or auth
enforcement breaks the first paint of the audit page.

The pre-existing tests in `test_032_admin_analytics.py` cover
auth-gate, three-source merge, source=vault filter, and invalid
source fallback. R69 adds boundary + contract tests:

- response shape contract: `{source, count, entries:[...]}`
- count/entries length agreement (count == len(entries))
- sort order: `entries[*].ts` is descending (newest first)
- source filters returning empty when the source has no rows
- limit slicing: `?limit=2` returns at most 2 entries
- limit=1 boundary
- limit=0 returns 0 entries (slicing semantics — not Pydantic 422)
- huge `?limit` is a no-op slice (no DoS, no error)
- entries carry the right per-source keys (vault → target/detail;
  customer → license_jti/detail; webhook → event_id/event_type/error)
- non-admin authorization (401) without a Bearer token

All tests use the same admin-login + monkeypatch pattern as the
sibling 032 suite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import (
    CustomerAuditEntry,
    VaultAuditEntry,
    WebhookEvent,
)
from app.db.session import get_engine


def _set_password(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )


def _login(client, monkeypatch) -> str:
    _set_password(monkeypatch, "s3cret")
    return client.post("/v1/admin/login", json={"password": "s3cret"}).json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


@pytest.fixture
def _seed_three_sources():
    """Seed one row per source with strictly-monotone timestamps so
    we can assert the descending-sort contract deterministically.
    Each test gets a uuid-suffixed `event_id` / `license_jti` so the
    fixture is safe to call from multiple tests in the same session
    without UNIQUE-constraint collisions on `webhook_events.event_id`.
    """
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:10]
    with Session(get_engine()) as db:
        db.add(
            VaultAuditEntry(
                action="r69_rotate",
                actor="admin",
                target_key=f"r69.age.key.{suffix}",
                hmac="a" * 64,
                prev_hmac="",
                ts=now - timedelta(minutes=1),  # newest
            )
        )
        db.add(
            CustomerAuditEntry(
                license_jti=f"r69_jti_customer_{suffix}",
                action="r69_tool_call",
                ts=now - timedelta(minutes=5),  # middle
            )
        )
        db.add(
            WebhookEvent(
                event_id=f"r69_evt_webhook_{suffix}",
                event_type="r69.checkout.session.completed",
                received_at=now - timedelta(minutes=10),  # oldest
            )
        )
        db.commit()
    yield suffix


def test_q12_r69_response_shape_contract(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"source", "count", "entries"}
    assert isinstance(body["entries"], list)


def test_q12_r69_count_matches_entries_length(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["count"] == len(body["entries"])


def test_q12_r69_descending_sort_order(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    timestamps = [row["ts"] for row in body["entries"] if row.get("ts")]
    assert timestamps == sorted(timestamps, reverse=True)


def test_q12_r69_source_filter_customer_only(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent?source=customer",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["source"] == "customer"
    for row in body["entries"]:
        assert row["source"] == "customer"


def test_q12_r69_source_filter_webhook_only(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent?source=webhook",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["source"] == "webhook"
    for row in body["entries"]:
        assert row["source"] == "webhook"


def test_q12_r69_limit_slicing_two(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent?limit=2",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(body["entries"]) <= 2
    assert body["count"] <= 2


def test_q12_r69_limit_one_boundary(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(body["entries"]) <= 1


def test_q12_r69_limit_zero_returns_empty(client, monkeypatch, _seed_three_sources):
    """`?limit=0` is a request for zero entries. The endpoint slices
    with Python's `out[:0] == []`, so the contract is an empty list,
    not a 422. If we ever add a Pydantic Field cap (`ge=1`) this
    becomes a contract change — pin it now so the change is visible."""
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?limit=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["entries"] == []


def test_q12_r69_huge_limit_is_safe(client, monkeypatch, _seed_three_sources):
    """A huge limit must not 5xx, must not OOM. The slice bounds the
    response naturally (out[:huge] returns the full out list)."""
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?limit=999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["entries"], list)


def test_q12_r69_per_source_keys_present(client, monkeypatch, _seed_three_sources):
    token = _login(client, monkeypatch)
    suffix = _seed_three_sources
    body = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    # Look up the rows we just seeded by suffix — other tests in the
    # same db session may have left rows behind.
    rows_by_source = {}
    for row in body["entries"]:
        marker = (
            row.get("license_jti")
            or row.get("id")
            or row.get("resource")
            or ""
        )
        if isinstance(marker, str) and suffix in marker:
            rows_by_source[row["source"]] = row

    if "vault" in rows_by_source:
        assert rows_by_source["vault"]["action"] == "r69_rotate"
        assert rows_by_source["vault"]["resource"].endswith(suffix)
        assert rows_by_source["vault"]["actor"] == "admin"
    if "customer" in rows_by_source:
        assert rows_by_source["customer"]["license_jti"].endswith(suffix)
        assert rows_by_source["customer"]["action"] == "r69_tool_call"
        # Every source must carry a non-null actor — the panel's CSV export
        # and actor filter call string methods on it (would crash on None).
        assert rows_by_source["customer"]["actor"] == "customer"
    if "webhook" in rows_by_source:
        assert rows_by_source["webhook"]["id"].endswith(suffix)
        assert (
            rows_by_source["webhook"]["action"]
            == "r69.checkout.session.completed"
        )
        assert rows_by_source["webhook"]["actor"] == "system"


def test_q12_audit_actor_present_all_sources(
    client, monkeypatch, _seed_three_sources
):
    """Regression: customer + webhook entries used to omit `actor`, so the
    panel CSV export (`actor.replace(...)`) and actor filter crashed on
    undefined. Every row, regardless of source, must expose a string actor."""
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    for row in body["entries"]:
        assert isinstance(row.get("actor"), str) and row["actor"], (
            f"missing actor on {row.get('source')} entry: {row}"
        )


def test_q12_audit_customer_resource_and_webhook_detail_passthrough(
    client, monkeypatch
):
    """Customer `resource` and webhook `error` columns exist on the models but
    were dropped by the feed; the panel reads `resource`/`detail`. Assert they
    now surface so the audit trail isn't silently blank."""
    suffix = uuid.uuid4().hex[:10]
    with Session(get_engine()) as db:
        db.add(
            CustomerAuditEntry(
                license_jti=f"res_jti_{suffix}",
                action="data_export",
                resource=f"export/{suffix}",
            )
        )
        db.add(
            WebhookEvent(
                event_id=f"err_evt_{suffix}",
                event_type="invoice.payment_failed",
                error=f"card_declined_{suffix}",
            )
        )
        db.commit()
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    by_id = {r.get("id"): r for r in body["entries"]}
    cust = next(
        (r for r in body["entries"] if r.get("license_jti") == f"res_jti_{suffix}"),
        None,
    )
    assert cust is not None and cust["resource"] == f"export/{suffix}"
    wh = by_id.get(f"err_evt_{suffix}")
    assert wh is not None and wh["detail"] == f"card_declined_{suffix}"


def test_q12_r69_unauthenticated_returns_401(client):
    """No Authorization header → 401, never 5xx, never silent 200."""
    r = client.get("/v1/admin/audit/recent")
    assert r.status_code == 401


def test_verify_chain_endpoint_reports_real_integrity(client, monkeypatch):
    """The panel's "Verify chain" button used to be a hardcoded fake (a 400ms
    timer that always said OK). It now calls this endpoint, which recomputes
    the real HMAC chain. An intact chain must report ok=True with a real count."""
    from app.vault.audit_chain import append_entry

    # Sibling tests seed VaultAuditEntry rows with placeholder hmacs (not a real
    # chain); clear them so we verify a clean, properly-chained log.
    with Session(get_engine()) as db:
        for r in db.scalars(select(VaultAuditEntry)).all():
            db.delete(r)
        db.commit()
    append_entry(action="r69_vc_one", target_key="vc.key.1")
    append_entry(action="r69_vc_two", target_key="vc.key.2")
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/verify-chain",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["total_entries"] >= 2
    assert body["tampered_entry_id"] is None
    assert "elapsed_ms" in body


def test_verify_chain_endpoint_requires_admin(client):
    """Integrity verification is admin-only — no token → 401, not a silent 200."""
    r = client.get("/v1/admin/audit/verify-chain")
    assert r.status_code == 401
