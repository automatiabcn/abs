"""029 Modul A — Customer audit log helper.

Public API:
  - log_customer_action(license_jti, action, ...) — write a CustomerAuditEntry
  - hash_ip(ip) — deterministic SHA-256 (license_jti for IP not stored plaintext)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session

from app.config import settings
from app.db.models import CustomerAuditEntry
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def hash_ip(ip: str) -> str:
    """Salted SHA-256 of IP, truncated to 32 hex chars."""
    if not ip:
        return ""
    payload = (ip + settings.audit_ip_salt).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def log_customer_action(
    *,
    license_jti: str,
    action: str,
    resource: Optional[str] = None,
    detail: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Best-effort: log a customer action; swallows DB errors."""
    if not license_jti:
        return
    try:
        with Session(get_engine()) as db:
            db.add(
                CustomerAuditEntry(
                    license_jti=license_jti,
                    action=action,
                    resource=resource,
                    detail=(detail or "")[:512],
                    ip_hash=hash_ip(ip or ""),
                    user_agent_short=(user_agent or "")[:128],
                    ts=datetime.now(timezone.utc),
                )
            )
            db.commit()
    except Exception as exc:
        logger.info("[customer_audit] log skipped: %s", exc)
