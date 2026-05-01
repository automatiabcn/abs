"""GUARD 6 + GUARD 10 — RAG context injection (STUB).

Bu task'ta (007) gerçek RAG entegrasyonu yoktur; 009-rag task'ında bağlanacak.
MVP davranışı: Bash/Edit/Write için placeholder hint string'i döndürür,
gerçek index çağrısı `_lookup_stub()` fonksiyonunda — 009'da implement edilecek.

Feature parity: SERVER rag_inject.py'nin 208 satırının iskeleti korundu
(rate-limit + cache + tool filtresi + in-memory pattern).
"""

from __future__ import annotations

import os
from typing import List

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "rag_inject_rate.json"
_WINDOW_SEC = 300  # 5 dakika per path/pattern

# Bu task'ta RAG index yok; 009'da `app.rag.query` ile değişecek.
_STUB_PATTERNS = {
    "bash_analysis": [
        "Benzer analiz daha önce orchestrator/quick.py içinde yapılmış (SERVER),"
        " lookup henüz bu üründe aktif değil (009-rag)."
    ],
    "write_code": [
        "STUB: Benzer pattern sorgulanacak (009-rag aktif olduğunda)."
    ],
    "write_docs": [
        "STUB: Geçmiş docs örnekleri sorgulanacak (009-rag)."
    ],
}


def _lookup_stub(category: str) -> List[str]:
    """009-rag task'ında `app.rag.query(category, k=3)` ile değişecek."""
    return _STUB_PATTERNS.get(category, [])


def _category_for(tool: str, tool_input: dict) -> str:
    cmd = (tool_input or {}).get("command", "") or ""
    fp = (tool_input or {}).get("file_path", "") or ""
    content = (tool_input or {}).get("content", "") or ""

    if tool == "Bash" and any(k in cmd.lower() for k in ("analyze", "analiz", "compare", "filter", "aggregate")):
        return "bash_analysis"
    if tool in ("Write", "Edit"):
        ext = os.path.splitext(fp)[1].lower()
        if ext in (".py", ".ts", ".tsx", ".js", ".go", ".rs"):
            return "write_code"
        if ext in (".md", ".mdx"):
            return "write_docs"
    return ""


@safe_hook("rag_inject")
def maybe_rag_inject(tool: str, tool_input: dict) -> str:
    if tool not in ("Bash", "Write", "Edit"):
        return ""

    category = _category_for(tool, tool_input)
    if not category:
        return ""

    key = f"{tool}:{category}"
    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, key, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)

    hits = _lookup_stub(category)
    if not hits:
        return ""
    body = "\n- ".join(hits)
    return f"RAG CONTEXT (STUB — 009 sonrası aktif):\n- {body}"
