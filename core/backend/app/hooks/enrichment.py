# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Content enrichment quality gate.

A large Write to a docs/markup/source file is scored over six layers — size,
non-ASCII language ratio, code-block density, mixed-language content, long
paragraphs, and file type. Above the threshold the hook suggests running the
content through a quality pipeline before it is written.

Advisory only: the hook never blocks and never calls a model itself.
"""

from __future__ import annotations

import os
from typing import Dict

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "enrichment_rate.json"
_WINDOW_SEC = 600

_ENRICH_EXT = {".md", ".mdx", ".json", ".html", ".py", ".ts", ".tsx"}
_MIN_SIZE = 2000  # content below this many chars skips the gate entirely

# Turkish-specific letters. Their density is the cheap signal for "this text is
# not English", which selects the localized quality pipeline.
_TR_CHARS = "\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc"


def _score_layers(content: str, ext: str) -> Dict[str, float]:
    """Score each layer in 0..1, where higher means more in need of enrichment."""
    size = len(content)
    layers: Dict[str, float] = {}

    layers["size"] = min(1.0, size / 8000.0)

    tr = sum(1 for c in content if c in _TR_CHARS)
    layers["tr_ratio"] = min(1.0, tr / max(1, size) * 200)

    blocks = content.count("```")
    layers["code_blocks"] = min(1.0, blocks / 20.0)

    # Mixed language: non-English letters together with English stop words.
    common_en = sum(content.lower().count(w) for w in (" the ", " and ", " of ", " is "))
    layers["lang_mix"] = min(1.0, common_en / 50.0) if tr > 20 else 0.0

    long_lines = sum(1 for ln in content.splitlines() if len(ln) > 500)
    layers["long_paragraphs"] = min(1.0, long_lines / 5.0)

    layers["ext"] = 0.3 if ext in _ENRICH_EXT else 0.0

    return layers


def _aggregate(layers: Dict[str, float]) -> float:
    # Weighted mean; size and code-block density carry the most weight.
    if not layers:
        return 0.0
    weighted = (
        layers["size"] * 1.2
        + layers["tr_ratio"] * 0.8
        + layers["code_blocks"] * 1.2
        + layers["lang_mix"] * 0.6
        + layers["long_paragraphs"] * 0.8
        + layers["ext"] * 0.4
    )
    total_w = 1.2 + 0.8 + 1.2 + 0.6 + 0.8 + 0.4
    return round(weighted / total_w, 3)


@safe_hook("enrichment")
def maybe_enrichment_notice(tool: str, tool_input: dict) -> str:
    """Return a pipeline suggestion when the gate score reaches 0.45, else "".

    Hooks run synchronously, so this cannot invoke the pipeline itself — the
    caller decides whether to act on the suggestion.
    """
    if tool != "Write":
        return ""

    fp = (tool_input or {}).get("file_path", "") or ""
    content = (tool_input or {}).get("content", "") or ""
    if not fp or len(content) < _MIN_SIZE:
        return ""

    ext = os.path.splitext(fp)[1].lower()
    if ext not in _ENRICH_EXT:
        return ""

    rate = load_rate(_RATE_FILE)
    key = f"{os.path.basename(fp)}:{ext}"
    if not allow_once(rate, key, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)

    layers = _score_layers(content, ext)
    score = _aggregate(layers)
    if score < 0.45:
        return ""

    pipeline_hint = "qual_tr" if layers["tr_ratio"] >= 0.3 else "qual_code"
    if ext == ".md":
        pipeline_hint = "qual_tr" if layers["tr_ratio"] >= 0.2 else "qual_analysis"

    return (
        f"ENRICHMENT GATE ({score:.2f}/1.0): {os.path.basename(fp)} is large and "
        f"multi-layered. Consider running it through the mcp__abs__{pipeline_hint} "
        f"pipeline and writing the improved result instead "
        f"(layers: size={layers['size']:.2f}, tr={layers['tr_ratio']:.2f}, "
        f"code={layers['code_blocks']:.2f}, lang_mix={layers['lang_mix']:.2f}, "
        f"long={layers['long_paragraphs']:.2f})."
    )
