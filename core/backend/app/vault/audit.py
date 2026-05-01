"""013 — Vault audit log (JSONL append-only).

Cleartext value YAZILMAZ — sadece event tipi + key adi + opsiyonel meta.
Path: settings.data_dir/vault_audit.jsonl
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, List

from app.config import settings


def _audit_path() -> Path:
    p = Path(settings.data_dir) / "vault_audit.jsonl"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def log_event(event: str, key: str, **extra: Any) -> None:
    """Vault olayini audit log'a ekle. Cleartext value YAZMA."""
    entry = {"ts": time.time(), "event": event, "key": key, **extra}
    try:
        with open(_audit_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_recent(limit: int = 50) -> List[dict]:
    p = _audit_path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
        out: List[dict] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []
