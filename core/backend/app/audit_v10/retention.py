# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-046 — SOC2 audit log retention helpers (HMAC chain + S3 hand-off plan).

⚠ Activating the 7-year S3 retention policy in production is a MANUAL approval
gate per the v10 worker brief. This module ships the helpers + a dry-run
exporter so we can rehearse the policy locally; no S3 calls happen here.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "AuditRecord",
    "RetentionPlan",
    "AuditChain",
    "build_retention_plan",
    "verify_chain",
]


@dataclass(slots=True)
class AuditRecord:
    seq: int
    timestamp: str
    actor: str
    tenant_id: str
    action: str
    resource: str
    payload_digest: str
    prev_hmac: str
    hmac: str


@dataclass(slots=True)
class RetentionPlan:
    s3_bucket: str
    s3_prefix: str
    object_lock_mode: str  # "COMPLIANCE" | "GOVERNANCE"
    retain_days: int
    objects: list[str] = field(default_factory=list)


def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class AuditChain:
    """Append-only HMAC-linked audit ledger; persists to a JSON Lines file."""

    def __init__(
        self,
        *,
        secret: str,
        path: Path | str | None = None,
    ) -> None:
        if not secret:
            raise ValueError("audit chain secret required")
        self._secret = secret
        self._records: list[AuditRecord] = []
        self._path = Path(path) if path else None
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        import json

        for line in self._path.read_text("utf-8").splitlines():
            data = json.loads(line)
            self._records.append(AuditRecord(**data))

    def append(
        self,
        *,
        actor: str,
        tenant_id: str,
        action: str,
        resource: str,
        payload: dict,
    ) -> AuditRecord:
        seq = len(self._records) + 1
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds") + "Z"
        prev = self._records[-1].hmac if self._records else ""
        digest = hashlib.sha256(repr(sorted(payload.items())).encode()).hexdigest()
        material = f"{seq}|{ts}|{actor}|{tenant_id}|{action}|{resource}|{digest}|{prev}".encode()
        record = AuditRecord(
            seq=seq,
            timestamp=ts,
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            payload_digest=digest,
            prev_hmac=prev,
            hmac=_hmac(self._secret, material),
        )
        self._records.append(record)
        if self._path is not None:
            import json
            from dataclasses import asdict

            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def records(self) -> list[AuditRecord]:
        return list(self._records)


def verify_chain(records: list[AuditRecord], *, secret: str) -> list[int]:
    """Return seq numbers whose HMAC fails verification (empty list = clean)."""

    failures: list[int] = []
    prev = ""
    for r in records:
        material = (
            f"{r.seq}|{r.timestamp}|{r.actor}|{r.tenant_id}|{r.action}|"
            f"{r.resource}|{r.payload_digest}|{prev}"
        ).encode()
        if not hmac.compare_digest(_hmac(secret, material), r.hmac):
            failures.append(r.seq)
        prev = r.hmac
    return failures


def build_retention_plan(
    *,
    s3_bucket: str,
    audit_files: list[str],
    s3_prefix: str = "abs/audit/",
    retain_days: int = 365 * 7,  # SOC2 7-year retention
    object_lock_mode: str = "COMPLIANCE",
) -> RetentionPlan:
    if object_lock_mode not in {"COMPLIANCE", "GOVERNANCE"}:
        raise ValueError(f"unsupported object_lock_mode {object_lock_mode!r}")
    if retain_days < 1:
        raise ValueError("retain_days must be >= 1")
    return RetentionPlan(
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix.rstrip("/") + "/",
        object_lock_mode=object_lock_mode,
        retain_days=retain_days,
        objects=list(audit_files),
    )
