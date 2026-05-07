# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GUARD 11 — Delegation self-enforcement.

Bash inline `python3 -c` analiz + curl→python pipe + büyük docs Write tespiti.
Her pattern için 15dk rate-limit.
"""

from __future__ import annotations

import os
import re

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "delegate_nudge_rate.json"
_WINDOW_SEC = 900  # 15 dakika

_ANALYSIS_KW = (
    "analyze", "analiz", "calculate", "hesapla", "summari", "ozetle",
    "compare", "karsilastir", "sort", "siralama", "rank", "classify",
    "group by", "filter", "reduce", "aggregate", "statistic",
    "count distinct", "mean(", "median(", "stdev",
)
_EXCLUSION_KW = (
    "open(", "read()", "json.load", "yaml.safe_load", "import ast",
    "compile(", "py_compile", "sys.stdin", "__import__",
    "subprocess.", "os.path.exists", "print(json.",
)
_DOCS_PATTERNS = (
    "README", "SETUP", "GUIDE", "TROUBLESHOOTING", "CHANGELOG",
    "CONTRIBUTING", "ARCHITECTURE", "INSTALL",
)


@safe_hook("delegate_nudge")
def maybe_delegate_nudge(tool: str, tool_input: dict) -> str:
    rate = load_rate(_RATE_FILE)

    def _allow(key: str) -> bool:
        if allow_once(rate, key, _WINDOW_SEC):
            persist_rate(_RATE_FILE, rate)
            return True
        return False

    if tool == "Bash":
        cmd = (tool_input or {}).get("command", "") or ""
        if not cmd:
            return ""

        py_inline = re.search(
            r"(?:python3?|/Library/Frameworks/Python\.framework/[^\s]+/python3)\s+-c\s+['\"]([^'\"]{40,})",
            cmd,
        )
        if py_inline:
            body = py_inline.group(1).lower()
            is_analysis = any(k in body for k in _ANALYSIS_KW)
            is_file_op = any(k in body for k in _EXCLUSION_KW)
            is_long = len(py_inline.group(1)) > 150
            if (is_analysis or is_long) and not is_file_op:
                if _allow("py_inline"):
                    return (
                        "DELEGATE NUDGE (Task V): Inline python3 -c analiz tespit edildi. "
                        "KURAL: 5+ satır inline analiz/hesap yerine → ask \"...\" gptoss. "
                        "Örnek: ask \"Bu veriyi analiz et: [veri]\" gptoss. "
                        "Dosya okuma/syntax check inline kalabilir. 15dk içinde tekrar gelmez."
                    )

        if re.search(r"curl\s[^|]+\|\s*python3?\s+-c", cmd):
            if _allow("curl_py"):
                return (
                    "DELEGATE NUDGE (Task V): curl → python3 -c pipe tespit edildi. "
                    "KURAL: curl'ü kendin çalıştır, analizi ask \"...\" groq ile yap. "
                    "Basit JSON parse (.key) kendin yap; 3+ adım analiz → delege et."
                )

    if tool == "Write":
        fp = (tool_input or {}).get("file_path", "") or ""
        content = (tool_input or {}).get("content", "") or ""
        if not fp or not content:
            return ""

        fname = os.path.basename(fp).upper()
        is_docs = any(p in fname for p in _DOCS_PATTERNS) or fname.endswith(".MD")
        if not is_docs or len(content) <= 3000:
            return ""

        tr_chars = sum(1 for c in content if c in "çğıöşüÇĞİÖŞÜ")
        tr_ratio = tr_chars / max(len(content), 1)
        is_tr_heavy = tr_ratio > 0.005
        code_blocks = content.count("```")
        if code_blocks > 10:
            return ""

        key = "docs_tr" if is_tr_heavy else "docs_en"
        if _allow(key):
            model_hint = "qwen32b" if is_tr_heavy else "gptoss"
            return (
                f"DELEGATE NUDGE (Task V): Büyük docs dosyası ({len(content)} char, "
                f"{fname}). KURAL: Metin üretimi kendin yapma → "
                f"mcp__abs__ask_{model_hint} veya ask \"...\" {model_hint} ile ürettir, "
                f"sonucu Write ile dosyaya yaz. Dokümantasyon ücretsiz ve daha kaliteli."
            )

    return ""
