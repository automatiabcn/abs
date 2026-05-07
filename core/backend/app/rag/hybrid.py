# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""016 — RAG hybrid retrieval (BM25 keyword + cosine semantic, weighted fusion).

Cosine ile genis havuz cek (top_k * 6 veya min 30), BM25 ile yeniden sirala,
fusion `alpha_semantic * cos_n + (1 - alpha_semantic) * bm25_n` ile top_k.

`alpha_semantic` 0.0 → sadece BM25, 1.0 → sadece cosine, default 0.6.
Min-max normalize iki skoru ortak skala'ya getirir.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from app.rag import embedding as _emb
from app.rag.indexer import _collection

logger = logging.getLogger(__name__)


_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _bm25_score(
    query_tokens: List[str],
    doc_tokens: List[str],
    avg_dl: float,
    doc_freqs: Dict[str, int],
    n_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Standart BM25 (k1=1.5, b=0.75)."""
    score = 0.0
    dl = len(doc_tokens)
    tf = Counter(doc_tokens)
    for q in query_tokens:
        if q not in doc_freqs:
            continue
        df = doc_freqs[q]
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        f = tf.get(q, 0)
        denom = f + k1 * (1 - b + b * dl / max(avg_dl, 1.0))
        if denom > 0:
            score += idf * (f * (k1 + 1)) / denom
    return score


def _normalize(arr: List[float]) -> List[float]:
    if not arr:
        return []
    mn, mx = min(arr), max(arr)
    if mx == mn:
        return [0.0 for _ in arr]
    return [(x - mn) / (mx - mn) for x in arr]


async def query_hybrid(
    question: str,
    project_filter: Optional[str] = None,
    top_k: int = 5,
    alpha_semantic: float = 0.6,
) -> List[Dict[str, Any]]:
    """BM25 + cosine fusion. Bos query → []. Embed/Chroma fail → [{error: ...}]."""
    if not question or not question.strip():
        return []
    try:
        vec = await _emb.embed(question)
    except Exception as exc:
        return [{"error": f"embed fail: {exc}"}]
    coll = _collection()
    where = {"project": project_filter} if project_filter else None
    pool_size = max(top_k * 6, 30)
    try:
        result = coll.query(query_embeddings=[vec], n_results=pool_size, where=where)
    except Exception as exc:
        return [{"error": f"chroma query fail: {exc}"}]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    if not docs:
        return []

    tokenized = [_tokenize(d) for d in docs]
    avg_dl = sum(len(t) for t in tokenized) / max(len(tokenized), 1)
    doc_freqs: Dict[str, int] = {}
    for toks in tokenized:
        for tok in set(toks):
            doc_freqs[tok] = doc_freqs.get(tok, 0) + 1
    q_toks = _tokenize(question)
    bm25_scores = [
        _bm25_score(q_toks, t, avg_dl, doc_freqs, len(docs)) for t in tokenized
    ]
    cosine_scores = [1.0 - float(d) if d is not None else 0.0 for d in dists]
    bm25_n = _normalize(bm25_scores)
    cos_n = _normalize(cosine_scores)

    fused = [
        (alpha_semantic * c + (1 - alpha_semantic) * bm)
        for c, bm in zip(cos_n, bm25_n)
    ]
    indexed = sorted(enumerate(fused), key=lambda x: -x[1])[:top_k]
    out: List[Dict[str, Any]] = []
    for idx, score in indexed:
        meta = metas[idx] if idx < len(metas) and metas[idx] else {}
        out.append(
            {
                "file": meta.get("file"),
                "project": meta.get("project"),
                "snippet": (docs[idx] or "")[:220],
                "score": round(float(score), 4),
                "bm25": round(float(bm25_scores[idx]), 3),
                "cosine": round(float(cosine_scores[idx]), 3),
            }
        )
    return out
