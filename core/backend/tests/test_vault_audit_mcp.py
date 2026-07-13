"""027 Modul F — `vault_audit_status` MCP tool."""

from __future__ import annotations

import asyncio
import json

from sqlmodel import Session, select

from app.db.models import VaultAuditEntry
from app.db.session import get_engine
from app.vault.audit_chain import append_entry


def _purge():
    with Session(get_engine()) as s:
        for r in s.scalars(select(VaultAuditEntry)).all():
            s.delete(r)
        s.commit()


def test_vault_audit_status_response_shape():
    _purge()
    append_entry(action="encrypt", target_key="t1")
    append_entry(action="decrypt", target_key="t1")
    append_entry(action="rotate", target_key="vault_master_key", detail="reason=manual")

    from app.mcp.tools.vault_audit_tools import vault_audit_status

    raw = asyncio.run(vault_audit_status(limit=10))
    out = json.loads(raw)
    for key in (
        "audit_chain_integrity",
        "tampered_entry_id",
        "verify_elapsed_ms",
        "total_entries",
        "entries_24h",
        "by_action",
        "recent",
    ):
        assert key in out, f"missing key: {key}"
    assert out["audit_chain_integrity"] == "ok"
    assert out["total_entries"] >= 3
    assert out["by_action"]["encrypt"] >= 1
    assert out["by_action"]["rotate"] >= 1


def test_vault_audit_status_reports_tamper():
    _purge()
    append_entry(action="encrypt", target_key="x")
    append_entry(action="decrypt", target_key="x")

    # Tamper with second entry
    with Session(get_engine()) as s:
        rows = list(
            s.scalars(select(VaultAuditEntry).order_by(VaultAuditEntry.id)).all()
        )
        rows[1].target_key = "tampered"
        s.add(rows[1])
        s.commit()

    from app.mcp.tools.vault_audit_tools import vault_audit_status

    out = json.loads(asyncio.run(vault_audit_status(limit=5)))
    assert out["audit_chain_integrity"] == "tampered"
    assert out["tampered_entry_id"] is not None


def test_vault_audit_status_recent_limit_respected():
    _purge()
    for i in range(20):
        append_entry(action="encrypt", target_key=f"k{i}")

    from app.mcp.tools.vault_audit_tools import vault_audit_status

    out = json.loads(asyncio.run(vault_audit_status(limit=5)))
    assert len(out["recent"]) == 5
