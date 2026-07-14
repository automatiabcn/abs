"""Audit chain + retention plan tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.audit_v10.retention import (
    AuditChain,
    build_retention_plan,
    verify_chain,
)


def test_audit_chain_append_and_verify(tmp_path: Path) -> None:
    chain = AuditChain(secret="sek", path=tmp_path / "audit.jsonl")
    chain.append(
        actor="alice",
        tenant_id="t1",
        action="rag.ingest",
        resource="doc:1",
        payload={"x": 1},
    )
    chain.append(
        actor="alice",
        tenant_id="t1",
        action="rag.query",
        resource="doc:1",
        payload={"q": "hi"},
    )
    assert verify_chain(chain.records(), secret="sek") == []


def test_audit_chain_round_trip_from_file(tmp_path: Path) -> None:
    p = tmp_path / "audit.jsonl"
    a = AuditChain(secret="sek", path=p)
    a.append(actor="u", tenant_id="t1", action="x", resource="r", payload={})
    b = AuditChain(secret="sek", path=p)
    assert len(b.records()) == 1
    assert verify_chain(b.records(), secret="sek") == []


def test_audit_chain_tamper_detected() -> None:
    chain = AuditChain(secret="sek")
    chain.append(actor="u", tenant_id="t1", action="x", resource="r", payload={"k": 1})
    chain.append(actor="u", tenant_id="t1", action="y", resource="r", payload={"k": 2})
    records = chain.records()
    records[0].action = "tampered"
    failures = verify_chain(records, secret="sek")
    assert failures == [1]


def test_audit_chain_requires_secret() -> None:
    with pytest.raises(ValueError):
        AuditChain(secret="")


def test_build_retention_plan_seven_year_default() -> None:
    plan = build_retention_plan(
        s3_bucket="abs-audit",
        audit_files=["audit-2026-04-28.jsonl"],
    )
    assert plan.retain_days == 365 * 7
    assert plan.object_lock_mode == "COMPLIANCE"
    assert plan.s3_prefix == "abs/audit/"


def test_build_retention_plan_rejects_unknown_lock_mode() -> None:
    with pytest.raises(ValueError):
        build_retention_plan(
            s3_bucket="abs-audit",
            audit_files=["a"],
            object_lock_mode="WHATEVER",
        )


def test_build_retention_plan_rejects_zero_retention() -> None:
    with pytest.raises(ValueError):
        build_retention_plan(
            s3_bucket="abs-audit",
            audit_files=["a"],
            retain_days=0,
        )


def test_audit_seq_is_strictly_increasing() -> None:
    chain = AuditChain(secret="sek")
    for i in range(5):
        chain.append(
            actor="u",
            tenant_id="t1",
            action=f"a{i}",
            resource="r",
            payload={"i": i},
        )
    seqs = [r.seq for r in chain.records()]
    assert seqs == [1, 2, 3, 4, 5]
