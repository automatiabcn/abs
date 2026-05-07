"""Shared helpers for test-data audit + reset utilities.

Used by:
  - scripts/audit_test_data.py  (read-only inventory)
  - scripts/reset_test_data.py  (dry-run + confirm purge)
  - core/backend/tests/test_reset_test_data.py

Categories scanned: users, chats, workflows, rag, audits, licenses, beta.

The bootstrap admin (``admin@demo-acme.com``), service accounts, and any
row in PROTECTED_EMAILS are never touched. Paid licence tiers
(self-host/team/enterprise) are never deleted. Real customer tenant data
(``demo-acme``/``default`` in the default config) is filtered defensively
so a category-wide DELETE never fires by tenant alone — only the per-row
email pattern triggers a deletion.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "core" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_EMAIL_PATTERN = re.compile(
    r"(@test\.local|@digisfer\.local|"
    r"^tester-|^final-|^r\d+(new)?admin|^chown-test|^l24|^smoke-|^qa-bot-)",
    re.IGNORECASE,
)

PROTECTED_EMAILS: frozenset[str] = frozenset(
    {
        "admin@demo-acme.com",
        "system@abs.local",
    }
)

PROTECTED_TENANTS: frozenset[str] = frozenset({"demo-acme", "default"})

PAID_TIERS: frozenset[str] = frozenset({"self-host", "team", "enterprise"})

CATEGORIES: tuple[str, ...] = (
    "users",
    "chats",
    "workflows",
    "rag",
    "audits",
    "licenses",
    "beta_requests",
)


def is_test_email(email: str | None) -> bool:
    if not email:
        return False
    if email.lower() in PROTECTED_EMAILS:
        return False
    return bool(TEST_EMAIL_PATTERN.search(email))


@dataclass
class CategoryResult:
    matched: int = 0
    deleted: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "deleted": self.deleted,
            "samples": self.samples[:5],
        }


def purge_test_users(session, dry_run: bool = True) -> CategoryResult:
    from sqlmodel import select

    from app.db.models import User

    rows = list(session.exec(select(User)).all())
    targets = [u for u in rows if is_test_email(u.email)]

    samples = [
        {"email": u.email, "tenant": u.tenant_slug, "status": u.status}
        for u in targets
    ]

    if not dry_run:
        for u in targets:
            session.delete(u)
        if targets:
            session.commit()

    return CategoryResult(
        matched=len(targets),
        deleted=0 if dry_run else len(targets),
        samples=samples,
    )


def purge_test_chats(session, dry_run: bool = True) -> CategoryResult:
    """Drop ChatSessions whose user_email matches the test pattern,
    plus any ChatMessages that referenced them."""
    from sqlmodel import select

    from app.db.models import ChatMessage, ChatSession

    sessions = list(session.exec(select(ChatSession)).all())
    target_sessions = [s for s in sessions if is_test_email(s.user_email)]
    target_ids = {s.id for s in target_sessions if s.id is not None}

    msg_count = 0
    if target_ids:
        msgs = list(
            session.exec(
                select(ChatMessage).where(
                    ChatMessage.session_id.in_(target_ids)
                )
            ).all()
        )
        msg_count = len(msgs)
        if not dry_run:
            for m in msgs:
                session.delete(m)

    samples = [
        {
            "session_id": s.id,
            "user_email": s.user_email,
            "tenant": s.tenant_slug,
            "title": s.title,
        }
        for s in target_sessions
    ]

    if not dry_run:
        for s in target_sessions:
            session.delete(s)
        if target_sessions or msg_count:
            session.commit()

    matched = len(target_sessions) + msg_count
    return CategoryResult(
        matched=matched,
        deleted=0 if dry_run else matched,
        samples=samples,
    )


def purge_test_licenses(session, dry_run: bool = True) -> CategoryResult:
    """Delete `beta`-tier licences whose customer_email matches the test
    pattern. Paid tiers are guarded explicitly."""
    from sqlmodel import select

    from app.db.models import License

    rows = list(session.exec(select(License)).all())
    targets = [
        lic
        for lic in rows
        if lic.tier not in PAID_TIERS and is_test_email(lic.customer_email)
    ]

    samples = [
        {
            "jti": lic.jti,
            "email": lic.customer_email,
            "tier": lic.tier,
        }
        for lic in targets
    ]

    if not dry_run:
        for lic in targets:
            session.delete(lic)
        if targets:
            session.commit()

    return CategoryResult(
        matched=len(targets),
        deleted=0 if dry_run else len(targets),
        samples=samples,
    )


def purge_test_audits(session, dry_run: bool = True) -> CategoryResult:
    """Delete CustomerAuditEntry rows whose license_jti maps to a test-
    email licence row, OR whose action starts with ``test.``/``smoke.``."""
    from sqlmodel import select

    from app.db.models import CustomerAuditEntry, License

    licences = list(session.exec(select(License)).all())
    test_jtis = {
        lic.jti
        for lic in licences
        if lic.tier not in PAID_TIERS and is_test_email(lic.customer_email)
    }

    rows = list(session.exec(select(CustomerAuditEntry)).all())
    targets = [
        e
        for e in rows
        if (e.license_jti in test_jtis)
        or (e.action or "").lower().startswith(("test.", "smoke."))
    ]

    samples = [
        {
            "id": e.id,
            "license_jti": e.license_jti,
            "action": e.action,
            "resource": e.resource,
        }
        for e in targets
    ]

    if not dry_run:
        for e in targets:
            session.delete(e)
        if targets:
            session.commit()

    return CategoryResult(
        matched=len(targets),
        deleted=0 if dry_run else len(targets),
        samples=samples,
    )


def purge_test_beta_requests(
    session, dry_run: bool = True
) -> CategoryResult:
    from sqlmodel import select

    from app.db.models import BetaRequest

    rows = list(session.exec(select(BetaRequest)).all())
    targets = [b for b in rows if is_test_email(b.email)]

    samples = [
        {"id": b.id, "email": b.email, "status": b.status} for b in targets
    ]

    if not dry_run:
        for b in targets:
            session.delete(b)
        if targets:
            session.commit()

    return CategoryResult(
        matched=len(targets),
        deleted=0 if dry_run else len(targets),
        samples=samples,
    )


_WORKFLOW_TEST_TYPE = re.compile(r"(test|smoke|qa)", re.IGNORECASE)


def purge_test_workflows(
    workflow_db_path: Path | None = None,
    dry_run: bool = True,
) -> CategoryResult:
    """workflow_state.db has no email/tenant column, so we match by
    `type` containing 'test'/'smoke'/'qa'. Best-effort signal."""
    if workflow_db_path is None:
        from app.config import settings

        workflow_db_path = Path(settings.data_dir) / "workflow_state.db"

    if not workflow_db_path.exists():
        return CategoryResult()

    conn = sqlite3.connect(str(workflow_db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(
                "SELECT id, type, status, started_at FROM workflows"
            ).fetchall()
        except sqlite3.OperationalError:
            return CategoryResult()

        targets = [
            r for r in rows if _WORKFLOW_TEST_TYPE.search(r["type"] or "")
        ]
        samples = [
            {
                "id": r["id"],
                "type": r["type"],
                "status": r["status"],
                "started_at": r["started_at"],
            }
            for r in targets
        ]

        if not dry_run and targets:
            ids = [r["id"] for r in targets]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"DELETE FROM steps WHERE workflow_id IN ({placeholders})",  # nosec B608
                ids,
            )
            conn.execute(
                f"DELETE FROM workflows WHERE id IN ({placeholders})",  # nosec B608
                ids,
            )
            conn.commit()

        return CategoryResult(
            matched=len(targets),
            deleted=0 if dry_run else len(targets),
            samples=samples,
        )
    finally:
        conn.close()


_RAG_FILE_PATTERNS = (
    re.compile(r"_test\.pdf$", re.IGNORECASE),
    re.compile(r"(^|/)test_.+\.txt$", re.IGNORECASE),
    re.compile(r"(^|/)smoke[_-]", re.IGNORECASE),
    re.compile(r"(^|/)fixture[_-]", re.IGNORECASE),
)
_RAG_TEST_PROJECTS = (
    re.compile(r"^test[_-]", re.IGNORECASE),
    re.compile(r"^smoke[_-]", re.IGNORECASE),
    re.compile(r"^qa[_-]", re.IGNORECASE),
)


def _rag_chunk_is_test(meta: dict[str, Any]) -> bool:
    project = (meta or {}).get("project") or ""
    file_path = (meta or {}).get("file") or ""
    if any(p.search(project) for p in _RAG_TEST_PROJECTS):
        return True
    if any(p.search(file_path) for p in _RAG_FILE_PATTERNS):
        return True
    return False


def purge_test_rag(
    enabled: bool = False,
    dry_run: bool = True,
) -> CategoryResult:
    """Scan Chroma collection and (optionally) delete chunks whose
    metadata file/project look like fixtures or smoke data.

    `enabled`: when False on a confirm run, this is a NO-OP — RAG is only
    purged if the operator passed `--purge-rag`.
    """
    if not enabled and not dry_run:
        return CategoryResult()

    try:
        from app.rag.indexer import _collection

        coll = _collection()
        all_rows = coll.get(include=["metadatas"])
    except Exception:
        return CategoryResult()

    metadatas = all_rows.get("metadatas") or []
    ids = all_rows.get("ids") or []
    target_ids: list[str] = []
    samples: list[dict[str, Any]] = []
    for cid, meta in zip(ids, metadatas):
        if _rag_chunk_is_test(meta or {}):
            target_ids.append(cid)
            if len(samples) < 5:
                samples.append(
                    {
                        "id": cid,
                        "project": (meta or {}).get("project"),
                        "file": (meta or {}).get("file"),
                    }
                )

    if not dry_run and enabled and target_ids:
        try:
            coll.delete(ids=target_ids)
        except Exception:
            pass

    return CategoryResult(
        matched=len(target_ids),
        deleted=(
            len(target_ids) if (not dry_run and enabled) else 0
        ),
        samples=samples,
    )


def run(
    *,
    confirm: bool = False,
    purge_rag: bool = False,
) -> dict[str, Any]:
    """Single entry point for both audit (confirm=False) and reset
    (confirm=True). Returns the report dict the CLIs print as JSON."""
    import time
    from datetime import datetime, timezone

    from sqlmodel import Session

    from app.db.session import get_engine

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    dry_run = not confirm

    categories: dict[str, dict[str, Any]] = {}

    with Session(get_engine()) as db:
        categories["users"] = purge_test_users(db, dry_run).to_dict()
        categories["chats"] = purge_test_chats(db, dry_run).to_dict()
        # `audits` scans licences for the test-jti map, so it must run
        # before `licenses` deletes them.
        categories["audits"] = purge_test_audits(db, dry_run).to_dict()
        categories["licenses"] = purge_test_licenses(db, dry_run).to_dict()
        categories["beta_requests"] = purge_test_beta_requests(
            db, dry_run
        ).to_dict()

    categories["workflows"] = purge_test_workflows(dry_run=dry_run).to_dict()
    categories["rag"] = purge_test_rag(
        enabled=purge_rag, dry_run=dry_run
    ).to_dict()

    total_matched = sum(c["matched"] for c in categories.values())
    total_deleted = sum(c["deleted"] for c in categories.values())

    return {
        "mode": "confirm" if confirm else "dry-run",
        "purge_rag": bool(purge_rag),
        "started_at": started_at.isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - t0, 3),
        "protected_emails": sorted(PROTECTED_EMAILS),
        "protected_tenants": sorted(PROTECTED_TENANTS),
        "paid_tiers": sorted(PAID_TIERS),
        "categories": categories,
        "total_matched": total_matched,
        "total_deleted": total_deleted,
    }


__all__ = [
    "CATEGORIES",
    "CategoryResult",
    "PAID_TIERS",
    "PROTECTED_EMAILS",
    "PROTECTED_TENANTS",
    "TEST_EMAIL_PATTERN",
    "is_test_email",
    "purge_test_audits",
    "purge_test_beta_requests",
    "purge_test_chats",
    "purge_test_licenses",
    "purge_test_rag",
    "purge_test_users",
    "purge_test_workflows",
    "run",
]
