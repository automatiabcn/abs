"""Q12-R91 — Final acceptance E2E (combined fresh deploy → first customer).

Single Playwright-style scenario consolidating R78 (setup wizard 12-step),
R85 (provider degradation 3-free-missing), R86 (license JWT lifecycle), and
R87 (multi-admin magic-link signup) into one chain. PASS = tester teslimat
eşik MÜHÜRLÜ.

Six phases (one test, sequential cookie state):

  PHASE 1 — setup wizard 6-step (admin + license + domain + anthropic +
            providers + test). Mirrors R78.
  PHASE 2 — provider degradation: 3 free missing (Cerebras + Cohere +
            Cloudflare empty), expect configured_count=3 + cascade gated 503.
            Mirrors R85's `3_free_missing` row.
  PHASE 3 — license JWT lifecycle: activate via /v1/license/activate,
            mark JTI revoked at the DB row, /v1/license/status reports
            "revoked", reactivate via fresh JWT mint. Mirrors R86 revoke path.
  PHASE 4 — multi-admin: Admin A signup + claim, Admin B signup + claim,
            both rows present in the same tenant. Mirrors R87.
  PHASE 5 — first chat session: POST /v1/chat/sessions + GET list.
  PHASE 6 — failure recovery: drop Groq key → /v1/cascade/providers reports
            it missing + active drops → re-add → providers green again.

Tests are written so that any single phase failing surfaces a *specific*
assertion line, not an opaque green/red — the tester can land on the broken
phase quickly. Helper assertions are inlined intentionally; this is a
seal-the-bridge test, not a reusable harness.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.licensing import generate_license, verify_license


REAL_KEY = "real-final-acceptance-AAAAAAAA"


@pytest.fixture()
def _fresh_state(tmp_path, monkeypatch):
    """Reset setup state to step 1 / not-completed for the run."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_file = tmp_path / "setup_state.json"
    state_file.write_text(
        json.dumps(
            {
                "completed": False,
                "current_step": 1,
                "completed_steps": [],
                "started_at": time.time(),
                "completed_at": None,
                "lang": "en",
                "data": {
                    "admin": None,
                    "license": None,
                    "domain": None,
                    "anthropic_configured": False,
                    "providers_configured": [],
                    "test_results": {},
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path, state_file


def _walk_setup(client, *, admin_email: str, admin_password: str) -> None:
    """Run the 6 setup steps so the post-setup APIs are reachable."""
    license_token = generate_license(
        customer_id="cus_r91_final", tier="self-host", seat_count=1
    )
    r = client.post(
        "/v1/setup/step/admin",
        json={"email": admin_email, "password": admin_password},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/setup/step/license", json={"license_key": license_token}
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/setup/step/domain",
        json={"mode": "ip", "domain": None, "ssl_mode": "internal"},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/setup/step/anthropic",
        json={"anthropic_api_key": "sk-ant-mock-r91-final"},
    )
    assert r.status_code == 200, r.text
    r = client.post("/v1/setup/step/providers", json={})
    assert r.status_code == 200, r.text
    r = client.post("/v1/setup/step/test", json={})
    assert r.status_code == 200, r.text


def test_r91_final_acceptance_combined(client, _fresh_state, monkeypatch):
    """Tek E2E senaryo, 6 phase. PASS = tester teslimat eşik mühürlü."""
    _tmp, state_file = _fresh_state
    assert _tmp.exists()
    admin_email = "founder@r91.local"
    admin_password = "FinalAcceptance2026!"

    # ────────────────────────────────────────────────────────────────────
    # PHASE 1 — setup wizard 6-step
    # ────────────────────────────────────────────────────────────────────
    r0 = client.get("/v1/setup/status")
    assert r0.status_code == 200
    assert r0.json()["completed"] is False, "fixture must boot incomplete"

    _walk_setup(
        client,
        admin_email=admin_email,
        admin_password=admin_password,
    )

    final_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_state["completed"] is True, "PHASE 1: setup must complete"

    r_login = client.post(
        "/auth/login",
        json={"email": admin_email, "password": admin_password},
    )
    assert r_login.status_code == 200, r_login.text
    assert r_login.json()["status"] == "logged_in"

    # ────────────────────────────────────────────────────────────────────
    # PHASE 2 — provider degradation: 3 free missing (Cerebras + Cohere + CF)
    # ────────────────────────────────────────────────────────────────────
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", REAL_KEY, raising=False)
    monkeypatch.setattr(settings, "groq_api_key", REAL_KEY, raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", REAL_KEY, raising=False)
    monkeypatch.setattr(settings, "cerebras_api_key", "", raising=False)
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    monkeypatch.setattr(settings, "cf_api_token", "", raising=False)

    r_prov = client.get("/v1/cascade/providers")
    assert r_prov.status_code == 200, r_prov.text
    prov = r_prov.json()
    assert prov["configured_count"] == 3, (
        f"PHASE 2: expected 3 configured, got {prov['configured_count']}"
    )
    assert prov["total"] == 6
    assert len(prov["active"]) == 3
    assert len(prov["missing"]) == 3
    # Names may be either bare ("cerebras") or attr-style ("cerebras_api_key");
    # accept either by substring.
    for must_be_missing in ("cerebras", "cohere"):
        assert any(must_be_missing in str(m).lower() for m in prov["missing"]), (
            f"PHASE 2: {must_be_missing!r} should be in missing[], "
            f"got {prov['missing']}"
        )

    # /v1/cascade/run with mock off — Founder Tester Round 2 (BUG-4) wired
    # the live cascade through `call_with_cascade`. Without real provider
    # keys the orchestrator raises ProviderError → 502 all_providers_failed.
    # If the chain happens to be entirely empty (config drift) the gate
    # still surfaces 503 no_providers_configured. Both shapes are
    # acceptable degradation surfaces for the R91 acceptance gate; the
    # contract under test is "no 200 escapes the unconfigured environment".
    r_run = client.post(
        "/v1/cascade/run",
        json={"prompt": "R91 phase 2 ping", "max_tokens": 8},
    )
    assert r_run.status_code in (502, 503), r_run.text
    detail = r_run.json().get("detail", "")
    assert (
        "all_providers_failed" in detail
        or "no_providers_configured" in detail
    ), f"PHASE 2: unexpected detail {detail!r}"

    # ────────────────────────────────────────────────────────────────────
    # PHASE 3 — license JWT lifecycle: activate → revoke → status → reactivate
    # ────────────────────────────────────────────────────────────────────
    activate_token = generate_license(
        customer_id="cus_r91_active", tier="self-host", seat_count=1, valid_days=30
    )
    r_act = client.post(
        "/v1/license/activate", json={"license_key": activate_token}
    )
    assert r_act.status_code == 200, r_act.text
    assert r_act.json()["status"] == "activated"

    payload = verify_license(activate_token)
    jti = payload["jti"]

    # Mark this JTI revoked at the DB row level (R86 revoke contract).
    from app.db.models import License
    from app.db.session import get_engine

    now_utc = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        existing = db.get(License, jti)
        if existing is None:
            db.add(
                License(
                    jti=jti,
                    customer_id="cus_r91_active",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now_utc,
                    expires_at=now_utc,
                    revoked_at=now_utc,
                    revoked_reason="r91_phase3",
                )
            )
        else:
            existing.revoked_at = now_utc
            existing.revoked_reason = "r91_phase3"
            db.add(existing)
        db.commit()

    settings.license_key = activate_token
    r_status_revoked = client.get("/v1/license/status")
    assert r_status_revoked.status_code == 200
    body_revoked = r_status_revoked.json()
    assert body_revoked["status"] == "revoked", (
        f"PHASE 3: expected status=revoked, got {body_revoked!r}"
    )
    assert body_revoked["jti"] == jti
    assert body_revoked["reason"] == "r91_phase3"

    # Reactivate by minting a fresh license — new JTI, no revoked row.
    reactivate_token = generate_license(
        customer_id="cus_r91_active",
        tier="self-host",
        seat_count=1,
        valid_days=30,
    )
    payload2 = verify_license(reactivate_token)
    assert payload2["jti"] != jti, "PHASE 3: reissue must mint a new JTI"
    r_reactivate = client.post(
        "/v1/license/activate", json={"license_key": reactivate_token}
    )
    assert r_reactivate.status_code == 200, r_reactivate.text
    r_status_active = client.get("/v1/license/status")
    assert r_status_active.status_code == 200
    assert r_status_active.json()["status"] == "active", (
        f"PHASE 3: post-reactivation expected active, got "
        f"{r_status_active.json()!r}"
    )

    # ────────────────────────────────────────────────────────────────────
    # PHASE 4 — multi-admin: A invites B, both in same tenant
    # ────────────────────────────────────────────────────────────────────
    from app.db.models import User

    r_a = client.post(
        "/auth/signup",
        json={
            "email": "admin_a@r91.local",
            "tenant_slug": "r91-tenant",
            "password": "TestPass2026!",
        },
    )
    assert r_a.status_code == 201, r_a.text
    link_a = r_a.json()["magic_link"]
    # Q12 honesty round: magic_link points at /activate (backend claim GET
    # /auth/magic below is unchanged).
    assert link_a.startswith("/activate?token=")
    token_a = link_a.split("token=", 1)[1]

    r_b = client.post(
        "/auth/signup",
        json={
            "email": "admin_b@r91.local",
            "tenant_slug": "r91-tenant",
            "password": "TestPass2026!",
        },
    )
    assert r_b.status_code == 201, r_b.text
    link_b = r_b.json()["magic_link"]
    token_b = link_b.split("token=", 1)[1]

    r_claim_a = client.get(f"/auth/magic?token={token_a}")
    assert r_claim_a.status_code == 200, r_claim_a.text
    assert r_claim_a.json()["status"] == "claimed"

    r_claim_b = client.get(f"/auth/magic?token={token_b}")
    assert r_claim_b.status_code == 200, r_claim_b.text
    assert r_claim_b.json()["status"] == "claimed"

    with Session(get_engine()) as db:
        rows = db.execute(
            select(User).where(User.tenant_slug == "r91-tenant")
        ).scalars().all()
    emails = sorted(u.email for u in rows)
    assert "admin_a@r91.local" in emails, (
        f"PHASE 4: admin_a missing from tenant rows {emails}"
    )
    assert "admin_b@r91.local" in emails, (
        f"PHASE 4: admin_b missing from tenant rows {emails}"
    )
    statuses = {u.email: u.status for u in rows}
    assert statuses["admin_a@r91.local"] == "active"
    assert statuses["admin_b@r91.local"] == "active"

    # PHASE 4 leaves admin_b's session cookie active — that is a valid
    # authenticated admin context for the panel APIs. PHASE 5/6 reuse it
    # rather than re-logging in as the founder (which would only re-prove
    # the login surface already covered by `r_login` above).

    # ────────────────────────────────────────────────────────────────────
    # PHASE 5 — first chat session
    # ────────────────────────────────────────────────────────────────────
    r_chat = client.post(
        "/v1/chat/sessions",
        json={"title": "R91 acceptance smoke chat"},
    )
    assert r_chat.status_code == 201, r_chat.text
    chat_id = r_chat.json()["id"]

    r_list = client.get("/v1/chat/sessions")
    assert r_list.status_code == 200
    sessions = r_list.json()
    assert any(s["id"] == chat_id for s in sessions), (
        "PHASE 5: created chat session missing from list"
    )

    # ────────────────────────────────────────────────────────────────────
    # PHASE 6 — failure recovery: drop Groq → providers reflects → re-add
    # ────────────────────────────────────────────────────────────────────
    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)
    r_drop = client.get("/v1/cascade/providers")
    assert r_drop.status_code == 200
    drop = r_drop.json()
    assert drop["configured_count"] == 2, (
        f"PHASE 6: expected 2 configured after groq drop, got "
        f"{drop['configured_count']}"
    )
    assert any(
        "groq" in str(m).lower() for m in drop["missing"]
    ), f"PHASE 6: groq must appear in missing[], got {drop['missing']}"

    # Re-add groq → returns to 3 configured, cascade contract green.
    monkeypatch.setattr(settings, "groq_api_key", REAL_KEY, raising=False)
    r_recovered = client.get("/v1/cascade/providers")
    assert r_recovered.status_code == 200
    rec = r_recovered.json()
    assert rec["configured_count"] == 3, (
        f"PHASE 6: post-recovery expected 3 configured, got "
        f"{rec['configured_count']}"
    )
    assert not any(
        "groq" in str(m).lower() for m in rec["missing"]
    ), f"PHASE 6: groq should be reactivated, still in missing {rec['missing']}"
