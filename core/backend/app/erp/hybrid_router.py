# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ERP hybrid retrieval router — classify a question as vector, sql, or both.

Routes to RAG, to text2SQL, or to both, and returns one `HybridAnswer` carrying
per-source provenance so the synthesis step can cite what it used.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "HybridAnswer",
    "RouteDecision",
    "classify_route",
    "hybrid_retrieve",
]


# Routing hints matched against the user's own words, in English and Turkish.
# Non-ASCII letters are escaped so the source stays ASCII; the values are what
# users actually type and must not be reworded.
_SQL_HINTS = (
    "ne kadar",
    "ka\u00e7",
    "toplam",
    "ortalama",
    "en \u00e7ok",
    "ge\u00e7en ay",
    "kim",
    "hangi m\u00fc\u015fteri",
    "fatura",
    "sipari\u015f",
    "ciro",
    "metric",
    "how many",
    "average",
    "total",
    "sum",
    "top ",
    "last month",
    "revenue",
    "kpi",
)
_RAG_HINTS = (
    "neden",
    "nas\u0131l",
    "a\u00e7\u0131kla",
    "\u00f6zetle",
    "bul",
    "\u00f6\u011fren",
    "why",
    "how does",
    "explain",
    "summarize",
    "find",
    "search",
)


@dataclass(slots=True)
class RouteDecision:
    route: str  # "sql" | "rag" | "hybrid"
    reasons: list[str]


@dataclass(slots=True)
class HybridAnswer:
    route: str
    sql_result: dict[str, Any] | None
    rag_hits: list[dict[str, Any]]
    elapsed_ms: float
    notes: list[str]


def _hits(text: str, hints: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [h for h in hints if re.search(rf"\b{re.escape(h)}\b", lowered)]


def classify_route(question: str) -> RouteDecision:
    sql_hits = _hits(question, _SQL_HINTS)
    rag_hits = _hits(question, _RAG_HINTS)
    if sql_hits and rag_hits:
        return RouteDecision(
            route="hybrid",
            reasons=[
                f"sql_hint:{','.join(sql_hits)}",
                f"rag_hint:{','.join(rag_hits)}",
            ],
        )
    if sql_hits:
        return RouteDecision(route="sql", reasons=[f"sql_hint:{','.join(sql_hits)}"])
    if rag_hits:
        return RouteDecision(route="rag", reasons=[f"rag_hint:{','.join(rag_hits)}"])
    # default to RAG when ambiguous; cheaper than running text2SQL on noise.
    return RouteDecision(route="rag", reasons=["default"])


def hybrid_retrieve(
    question: str,
    *,
    tenant_id: str,
    rag_search: Any,
    text2sql_generate: Any,
    rag_limit: int = 5,
) -> HybridAnswer:
    started = time.perf_counter()
    decision = classify_route(question)
    notes: list[str] = decision.reasons.copy()
    rag_hits: list[dict[str, Any]] = []
    sql_result: dict[str, Any] | None = None

    if decision.route in {"rag", "hybrid"}:
        try:
            rag_hits = rag_search(
                question=question, tenant_id=tenant_id, limit=rag_limit
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"rag_error:{exc}")

    if decision.route in {"sql", "hybrid"}:
        try:
            generated = text2sql_generate(question)
            sql_result = {
                "sql": generated.sql,
                "explanation": generated.explanation,
                "confidence": generated.confidence,
                "backend": generated.backend,
            }
        except Exception as exc:  # noqa: BLE001
            notes.append(f"sql_error:{exc}")

    elapsed = (time.perf_counter() - started) * 1000.0
    logger.info(
        "hybrid_route route=%s tenant=%s rag=%d sql=%s ms=%.1f",
        decision.route,
        tenant_id,
        len(rag_hits),
        bool(sql_result),
        elapsed,
    )
    return HybridAnswer(
        route=decision.route,
        sql_result=sql_result,
        rag_hits=rag_hits,
        elapsed_ms=elapsed,
        notes=notes,
    )
