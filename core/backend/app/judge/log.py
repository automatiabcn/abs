"""Judge JSONL log + outcome update + log rotation.

SERVER orchestrator/judge_log.py portu. Her `judge_diff` çağrısı bir kayıt yazar,
müşteri/Claude sonradan accept|reject ile outcome işaretleyebilir.
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


def log_judgment(
    result: Dict[str, Any],
    file_path: Optional[str] = None,
    source: str = "judge_patch_tool",
) -> str:
    """Judgment kaydını JSONL'e ekle, ID döndür."""
    _rotate_if_large()
    judgment_id = uuid.uuid4().hex[:12]
    persona_drift = None
    try:
        # AST fingerprint detail varsa drift kabaca: ortalama mutlak fark
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


def update_outcome(judgment_id: str, outcome: str) -> bool:
    """Bir judgment kaydının outcome alanını in-place güncelle (accept/reject)."""
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
        if entry.get("id") == judgment_id:
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


def read_recent(limit: int = 50) -> List[Dict[str, Any]]:
    p = _log_path()
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out
