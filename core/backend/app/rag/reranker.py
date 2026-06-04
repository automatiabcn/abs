# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-013 — Cross-encoder reranker (Qwen3-Reranker-4B + Cohere fallback + mock).

Default backend is "mock" (pure-stdlib lexical overlap) so tests work offline.
Real backends are gated behind deferred imports. Includes a tiny in-process
LRU+TTL cache keyed on (backend, query, doc-hash) — no Redis dependency for
Sprint 3; production can swap by writing a `_RedisCache` adapter later.
"""

from __future__ import annotations

import collections
import hashlib
import logging
import time
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "Reranker",
    "RerankResult",
    "cache_stats",
    "close_reranker",
    "get_reranker",
]


@dataclass(slots=True)
class RerankResult:
    index: int
    score: float
    doc: str


class _MockBackend:
    def __init__(self) -> None:
        logger.info("rerank_mock_init")

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _score_pairs(self, query: str, docs: list[str]) -> list[float]:
        q_tokens = set(query.lower().split())
        q_lower = query.lower()
        scores: list[float] = []
        for doc in docs:
            d_tokens = set(doc.lower().split())
            base = self._jaccard(q_tokens, d_tokens)
            boost = 0.05 if q_lower and q_lower in doc.lower() else 0.0
            scores.append(base + boost)
        return scores

    def close(self) -> None:
        return None


class _Qwen3OnnxBackend:
    def __init__(self, model_path: str, providers: list[str]) -> None:
        if not model_path:
            raise ValueError(
                "rerank_model_path must be set for the qwen3_onnx backend"
            )
        try:
            import onnxruntime as ort  # noqa: F401
            from transformers import AutoTokenizer  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "qwen3_onnx backend requires `onnxruntime` and `transformers`"
            ) from exc

        import onnxruntime as ort
        from transformers import AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-4B")
        self._session = ort.InferenceSession(model_path, providers=providers)
        logger.info("rerank_qwen3_onnx_init providers=%s", providers)

    def _score_pairs(self, query: str, docs: list[str]) -> list[float]:
        inputs = [f"{query}\n{doc}" for doc in docs]
        enc = self._tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="np",
        )
        outputs = self._session.run(None, dict(enc))
        logits = outputs[0]
        return [float(s) for s in logits[:, 0].tolist()]

    def close(self) -> None:
        return None


class _CohereBackend:
    def __init__(self, *, model: str, api_key: str) -> None:
        if not api_key:
            raise ValueError("cohere_api_key must be set for the Cohere backend")
        try:
            import cohere  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "cohere backend requires the `cohere` package"
            ) from exc

        import cohere

        self._client = cohere.ClientV2(api_key=api_key)
        self._model = model
        logger.info("rerank_cohere_init model=%s", model)

    def _score_pairs(self, query: str, docs: list[str]) -> list[float]:
        response = self._client.rerank(
            query=query,
            documents=docs,
            model=self._model,
            top_n=len(docs),
        )
        index_to_score = {r.index: float(r.relevance_score) for r in response.results}
        return [index_to_score.get(i, 0.0) for i in range(len(docs))]

    def close(self) -> None:
        return None


class Reranker:
    backend: str

    def __init__(self, backend_name: str) -> None:
        self.backend = backend_name
        if backend_name == "mock":
            self._impl = _MockBackend()
        elif backend_name == "qwen3_onnx":
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if str(getattr(settings, "rerank_device", "cpu")).lower() == "cuda"
                else ["CPUExecutionProvider"]
            )
            self._impl = _Qwen3OnnxBackend(
                getattr(settings, "rerank_model_path", ""),
                providers=providers,
            )
        elif backend_name == "cohere":
            self._impl = _CohereBackend(
                model="rerank-v3.5",
                api_key=getattr(settings, "cohere_api_key", "") or "",
            )
        else:
            raise ValueError(f"unsupported rerank backend: {backend_name}")

        self._cache: "collections.OrderedDict[str, tuple[float, float]]" = (
            collections.OrderedDict()
        )
        self._stats: dict[str, int] = {"hits": 0, "misses": 0, "evictions": 0}

    @staticmethod
    def _key(backend: str, query_norm: str, doc: str) -> str:
        digest = hashlib.sha1(doc.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"{backend}|{query_norm}|{digest}"

    def rerank(
        self, query: str, docs: list[str], *, top_k: int = 3
    ) -> list[RerankResult]:
        if not docs:
            return []
        started = time.perf_counter()
        norm_query = query.strip().lower()
        now = time.time()
        ttl = int(getattr(settings, "rerank_cache_ttl_seconds", 3600))
        max_entries = int(getattr(settings, "rerank_cache_max_entries", 4096))

        scores: list[float] = [0.0] * len(docs)
        missing_idx: list[int] = []
        missing_docs: list[str] = []

        for i, doc in enumerate(docs):
            key = self._key(self.backend, norm_query, doc)
            entry = self._cache.get(key)
            if entry is not None and entry[1] > now:
                scores[i] = entry[0]
                self._stats["hits"] += 1
                self._cache.move_to_end(key)
            else:
                if entry is not None:
                    del self._cache[key]
                self._stats["misses"] += 1
                missing_idx.append(i)
                missing_docs.append(doc)

        if missing_docs:
            fresh = self._impl._score_pairs(query, missing_docs)
            for idx, sc in zip(missing_idx, fresh):
                scores[idx] = sc
                key = self._key(self.backend, norm_query, docs[idx])
                self._cache[key] = (sc, now + ttl)
                self._cache.move_to_end(key)

            evicted = 0
            while len(self._cache) > max_entries:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1
                evicted += 1
            if evicted > 100:
                logger.warning("rerank_cache_evictions n=%d", evicted)

        results = [
            RerankResult(index=i, score=scores[i], doc=docs[i])
            for i in range(len(docs))
        ]
        results.sort(key=lambda r: (-r.score, r.index))
        logger.debug(
            "rerank backend=%s top_k=%d hits=%d misses=%d ms=%.1f",
            self.backend,
            top_k,
            self._stats["hits"],
            self._stats["misses"],
            (time.perf_counter() - started) * 1000.0,
        )
        return results[:top_k]

    def close(self) -> None:
        try:
            self._impl.close()
        finally:
            self._cache.clear()


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        backend = getattr(settings, "rerank_backend", "mock") or "mock"
        try:
            _reranker = Reranker(backend)
        except Exception as exc:
            # e.g. rerank_backend=cohere but the operator hasn't entered a
            # Cohere key yet. Degrade to the mock reranker (dense order
            # preserved) instead of taking the whole RAG path down.
            logger.warning(
                "reranker backend %r unavailable (%s) — falling back to mock",
                backend,
                exc,
            )
            _reranker = Reranker("mock")
    return _reranker


def close_reranker() -> None:
    global _reranker
    if _reranker is None:
        return
    try:
        _reranker.close()
    finally:
        _reranker = None


def cache_stats() -> dict[str, int]:
    if _reranker is None:
        return {"hits": 0, "misses": 0, "evictions": 0, "size": 0}
    return {
        "hits": _reranker._stats.get("hits", 0),
        "misses": _reranker._stats.get("misses", 0),
        "evictions": _reranker._stats.get("evictions", 0),
        "size": len(_reranker._cache),
    }
