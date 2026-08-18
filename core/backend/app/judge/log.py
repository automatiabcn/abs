# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Judge JSONL log — append, outcome update, rotation.

Every `judge_diff` call writes one record. The outcome (accept|reject) is
recorded later, once the patch is acted on.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_ROTATE_BYTES = 5 * 1024 * 1024  # 5MB


def _log_path() -> Path:
    p = Path(settings.data_dir) / "judge_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _rotate_if_large() -> None:
    p = _log_path()
    try:
        if p.is_file() and p.stat().st_size > _ROTATE_BYTES:
            backup = p.with_suffix(".jsonl.1")
            if backup.exists():
                backup.unlink()
            p.rename(backup)
    except Exception:
        pass


def _caller_tenant() -> Optional[str]:
    """The MCP caller's tenant, when this runs inside an MCP call."""
    try:
        from app.mcp.context import mcp_tenant_id

        return mcp_tenant_id.get() or None
    except Exception:  # noqa: BLE001
        return None


def _visible(entry: Dict[str, Any], tenant: Optional[str]) -> bool:
    """A judgment belongs to the tenant that made it. Records written before
    the field existed have no owner and are visible to the default/global
    view only — never to a named tenant that did not write them."""
    if tenant is None:
        return True
    owner = entry.get("tenant")
    if owner is None:
        return tenant in ("default", "_global")
    return owner == tenant


def log_judgment(
    result: Dict[str, Any],
    file_path: Optional[str] = None,
    source: str = "judge_patch_tool",
    tenant: Optional[str] = None,
) -> str:
    """Append a judgment record and return its id. The record carries the
    tenant that produced it (2026-08-18: judge_recent handed every tenant's
    file paths and teaching to any token; judge_outcome let anyone flip
    anyone's record — the training signal)."""
    _rotate_if_large()
    judgment_id = uuid.uuid4().hex[:12]
    if tenant is None:
        tenant = _caller_tenant()
    persona_drift = None
    try:
        # With AST fingerprint detail, drift is roughly the mean absolute difference
        details = result.get("fingerprint_details") or []
        if details:
            diffs = [
                abs(float(d.get("actual", 0)) - float(d.get("target", 0)))
                for d in details
                if isinstance(d, dict)
            ]
            persona_drift = round(sum(diffs) / len(diffs), 3) if diffs else None
    except Exception:
        persona_drift = None

    entry = {
        "id": judgment_id,
        "ts": time.time(),
        "source": source,
        "tenant": tenant,
        "file": file_path,
        "ast_score": result.get("ast_score"),
        "llm_score": result.get("llm_score"),
        "combined_score": result.get("combined_score"),
        "persona_drift": persona_drift,
        "outcome": None,
    }
    p = _log_path()
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return judgment_id


def update_outcome(judgment_id: str, outcome: str, tenant: Optional[str] = None) -> bool:
    """Set the outcome (accept/reject) of an existing judgment record — one
    the caller's tenant owns. With `tenant` None (in-process caller) any
    record may be updated."""
    if outcome not in ("accept", "reject"):
        return False
    p = _log_path()
    if not p.is_file():
        return False
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    found = False
    new_lines: List[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            new_lines.append(line)
            continue
        if entry.get("id") == judgment_id and _visible(entry, tenant):
            entry["outcome"] = outcome
            entry["outcome_ts"] = time.time()
            found = True
            new_lines.append(json.dumps(entry, ensure_ascii=False))
        else:
            new_lines.append(line)
    if not found:
        return False
    tmp = p.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return True


def read_recent(limit: int = 50, tenant: Optional[str] = None) -> List[Dict[str, Any]]:
    """The last `limit` judgments visible to `tenant` (all, when None)."""
    p = _log_path()
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in reversed(p.read_text(encoding="utf-8").splitlines()):
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if not _visible(entry, tenant):
                continue
            out.append(entry)
            if len(out) >= limit:
                break
    except Exception:
        pass
    out.reverse()
    return out
