# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Delegation nudges.

Detects work that belongs on a provider rather than in the local shell: inline
`python3 -c` analysis, a curl output piped into python, and hand-written long
documentation. Each pattern is rate-limited so a session sees it at most once
per window.
"""

from __future__ import annotations

import os
import re

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "delegate_nudge_rate.json"
_WINDOW_SEC = 900

_ANALYSIS_KW = (
    "analyze",
    "analiz",
    "calculate",
    "hesapla",
    "summari",
    "ozetle",
    "compare",
    "karsilastir",
    "sort",
    "siralama",
    "rank",
    "classify",
    "group by",
    "filter",
    "reduce",
    "aggregate",
    "statistic",
    "count distinct",
    "mean(",
    "median(",
    "stdev",
)
_EXCLUSION_KW = (
    "open(",
    "read()",
    "json.load",
    "yaml.safe_load",
    "import ast",
    "compile(",
    "py_compile",
    "sys.stdin",
    "__import__",
    "subprocess.",
    "os.path.exists",
    "print(json.",
)
_DOCS_PATTERNS = (
    "README",
    "SETUP",
    "GUIDE",
    "TROUBLESHOOTING",
    "CHANGELOG",
    "CONTRIBUTING",
    "ARCHITECTURE",
    "INSTALL",
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
                        "ABS delegation: inline python analysis detected. "
                        "Delegate heavy analysis/compute to ABS instead of running "
                        "it locally — call mcp__abs__ask_gptoss (or mcp__abs__ask_qwen32b "
                        "for non-English). It runs on the operator's provider keys at "
                        "no extra cost. File reads / syntax checks can stay inline."
                    )

        if re.search(r"curl\s[^|]+\|\s*python3?\s+-c", cmd):
            if _allow("curl_py"):
                return (
                    "ABS delegation: curl | python pipe detected. Run the curl "
                    "yourself, but delegate the analysis of the output to "
                    "mcp__abs__ask_groq / mcp__abs__ask_gptoss. Simple JSON field "
                    "access (.key) is fine locally; 3+ step analysis → delegate."
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

        # Turkish-specific letters \u2014 their density picks the multilingual model.
        tr_chars = sum(
            1
            for c in content
            if c
            in "\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc"
        )
        tr_ratio = tr_chars / max(len(content), 1)
        is_tr_heavy = tr_ratio > 0.005
        code_blocks = content.count("```")
        if code_blocks > 10:
            return ""

        key = "docs_tr" if is_tr_heavy else "docs_en"
        if _allow(key):
            model_hint = "qwen32b" if is_tr_heavy else "gptoss"
            return (
                f"ABS delegation: large docs file ({len(content)} chars, {fname}). "
                f"Don't hand-write long prose — generate it via mcp__abs__ask_{model_hint}, "
                f"then write the result to the file. Runs on the operator's provider "
                f"keys at no extra cost and is usually higher quality."
            )

    return ""
