# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GUARD 3 — Content enrichment + quality gate.

Büyük docs/md/json/html/py/ts Write → quality gate (6 katman):
1. Boyut (size check)
2. Dil dağılımı (tr_ratio)
3. Teknik/metinsel kırılım (code block ratio)
4. Hedef dil tutarsızlığı
5. A/B test: mevcut içerik vs qual_code pipeline çıktısı
6. Geri dönüt kaydet (cache)

SERVER enrichment.py'nin davranış parity'si korunur, ürün ortamında
pipeline çağrısı 006'daki `QualCodePipeline` / `QualTrPipeline`'dan yapılır.
"""

from __future__ import annotations

import os
from typing import Dict

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "enrichment_rate.json"
_WINDOW_SEC = 600

_ENRICH_EXT = {".md", ".mdx", ".json", ".html", ".py", ".ts", ".tsx"}
_MIN_SIZE = 2000  # char; altındaki içerik gate atlanır


def _score_layers(content: str, ext: str) -> Dict[str, float]:
    """6-katman puan (0..1, yüksek = daha fazla enrichment ihtiyacı)."""
    size = len(content)
    layers: Dict[str, float] = {}

    # L1 — büyüklük
    layers["size"] = min(1.0, size / 8000.0)

    # L2 — tr ratio
    tr = sum(1 for c in content if c in "çğıöşüÇĞİÖŞÜ")
    layers["tr_ratio"] = min(1.0, tr / max(1, size) * 200)

    # L3 — code block ratio (Markdown için)
    blocks = content.count("```")
    layers["code_blocks"] = min(1.0, blocks / 20.0)

    # L4 — hedef dil tutarsızlığı: .md dosyasında tr chars + en stop words karışık
    common_en = sum(content.lower().count(w) for w in (" the ", " and ", " of ", " is "))
    layers["lang_mix"] = min(1.0, common_en / 50.0) if tr > 20 else 0.0

    # L5 — uzun paragraf (500+ char single line) sayısı
    long_lines = sum(1 for ln in content.splitlines() if len(ln) > 500)
    layers["long_paragraphs"] = min(1.0, long_lines / 5.0)

    # L6 — extension uygunluğu (ext listedeyse düşük ağırlık; değilse 0)
    layers["ext"] = 0.3 if ext in _ENRICH_EXT else 0.0

    return layers


def _aggregate(layers: Dict[str, float]) -> float:
    # Basit ortalama; ağırlıklar L1(size) + L3(code_blocks) biraz yüksek.
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
    """Quality gate skorunu hesaplayıp >=0.45 ise pipeline önerisi döndürür.

    Not: Gerçek pipeline çağrısı sync ortamda yapılmaz (hook senkron). Pipeline
    tetikleyici Claude Code tarafında, bu sadece tavsiye döndürür.
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
        f"ENRICHMENT GATE ({score:.2f}/1.0): {os.path.basename(fp)} büyük + "
        f"çok katmanlı içerik. Kalite yükseltmek için mcp__abs__{pipeline_hint} "
        f"pipeline'ından geçirip sonucu tekrar Write ile yazmak önerilir "
        f"(6 kat.: size={layers['size']:.2f}, tr={layers['tr_ratio']:.2f}, "
        f"code={layers['code_blocks']:.2f}, lang_mix={layers['lang_mix']:.2f}, "
        f"long={layers['long_paragraphs']:.2f})."
    )
