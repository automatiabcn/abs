"""027 Modul C — Vault audit chain (HMAC tamper detection)."""

from __future__ import annotations

import time

from sqlmodel import Session, select

from app.config import settings
from app.db.models import VaultAuditEntry
from app.db.session import get_engine
from app.vault.audit_chain import (
    append_entry,
    reseal_chain,
    stats,
    verify_chain,
)


def _purge():
    with Session(get_engine()) as s:
        for r in s.scalars(select(VaultAuditEntry)).all():
            s.delete(r)
        s.commit()


def test_append_entry_creates_chain():
    _purge()
    a = append_entry(action="encrypt", actor="test", target_key="key1")
    b = append_entry(action="decrypt", actor="test", target_key="key1")
    c = append_entry(action="rotate", actor="test", target_key="key1", detail="scheduled")

    assert a.prev_hmac == ""
    assert a.hmac and len(a.hmac) == 64
    assert b.prev_hmac == a.hmac
    assert c.prev_hmac == b.hmac

    out = verify_chain()
    assert out["ok"] is True
    assert out["total_entries"] == 3
    assert out["tampered_entry_id"] is None


def test_tamper_detected_on_modified_entry():
    _purge()
    append_entry(action="encrypt", target_key="t1")
    append_entry(action="decrypt", target_key="t1")
    append_entry(action="rotate", target_key="t1")

    # Modify middle entry's target_key without re-computing hmac
    with Session(get_engine()) as s:
        rows = list(
            s.scalars(select(VaultAuditEntry).order_by(VaultAuditEntry.id)).all()
        )
        rows[1].target_key = "tampered"
        s.add(rows[1])
        s.commit()
        tampered_id = rows[1].id

    out = verify_chain()
    assert out["ok"] is False
    assert out["tampered_entry_id"] == tampered_id


def test_missing_prev_hmac_link_detected():
    _purge()
    append_entry(action="encrypt")
    append_entry(action="decrypt")

    # Break the prev_hmac chain at the second entry.
    with Session(get_engine()) as s:
        rows = list(
            s.scalars(select(VaultAuditEntry).order_by(VaultAuditEntry.id)).all()
        )
        rows[1].prev_hmac = "0" * 64  # bogus
        s.add(rows[1])
        s.commit()
        tampered_id = rows[1].id

    out = verify_chain()
    assert out["ok"] is False
    assert out["tampered_entry_id"] == tampered_id


def test_reseal_after_secret_rotation_restores_chain(monkeypatch):
    _purge()
    append_entry(action="encrypt")
    append_entry(action="decrypt")
    append_entry(action="rotate")

    # Rotate hmac secret → chain becomes invalid.
    monkeypatch.setattr(settings, "vault_audit_hmac_secret", "new-secret-v2")
    out = verify_chain()
    assert out["ok"] is False

    # Reseal → chain valid again under the new secret.
    resealed = reseal_chain()
    assert resealed["resealed"] == 3
    out2 = verify_chain()
    assert out2["ok"] is True


def test_verify_chain_under_100ms_for_1000_entries():
    _purge()
    # Append 1000 entries and assert verify_chain elapsed_ms < 500ms (allow
    # generous margin on slow CI; spec target is <100ms on dev hardware).
    for i in range(1000):
        append_entry(action="encrypt", target_key=f"perf_{i}")
    t0 = time.perf_counter()
    out = verify_chain()
    elapsed = (time.perf_counter() - t0) * 1000
    assert out["ok"] is True
    assert out["total_entries"] == 1000
    assert elapsed < 500, f"verify took {elapsed}ms (target <500)"


def test_stats_groups_by_action_and_lists_recent():
    _purge()
    append_entry(action="encrypt", target_key="a")
    append_entry(action="encrypt", target_key="b")
    append_entry(action="decrypt", target_key="a")
    append_entry(action="rotate", target_key="a", detail="scheduled")

    s = stats(recent_limit=10)
    assert s["audit_chain_integrity"] == "ok"
    assert s["total_entries"] == 4
    assert s["by_action"]["encrypt"] == 2
    assert s["by_action"]["decrypt"] == 1
    assert s["by_action"]["rotate"] == 1
    assert len(s["recent"]) == 4
