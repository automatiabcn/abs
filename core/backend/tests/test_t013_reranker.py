"""Cross-encoder reranker tests (mock backend, cache, fallback gates)."""

from __future__ import annotations

import time

import pytest

from app.config import settings
from app.rag import reranker as rr
from app.rag.reranker import Reranker, RerankResult


@pytest.fixture(autouse=True)
def _reset() -> None:
    rr.close_reranker()
    yield
    rr.close_reranker()


def test_rerank_returns_top_k_sorted_descending() -> None:
    r = Reranker("mock")
    docs = ["nothing here", "abs rag platform", "random text", "quick rag overview"]
    res = r.rerank("abs rag", docs, top_k=2)
    assert len(res) == 2
    assert res[0].score >= res[1].score
    assert {x.doc for x in res}.issubset(set(docs))


def test_rerank_empty_docs_returns_empty() -> None:
    assert Reranker("mock").rerank("q", [], top_k=5) == []


def test_rerank_top_k_capped_at_doc_count() -> None:
    r = Reranker("mock")
    res = r.rerank("any", ["doc1", "doc2"], top_k=10)
    assert len(res) == 2


def test_rerank_score_uses_substring_boost() -> None:
    r = Reranker("mock")
    docs = ["abs is here", "unrelated word"]
    res = r.rerank("abs", docs, top_k=2)
    assert res[0].doc == docs[0]
    assert res[0].score >= 0.05


def test_rerank_ties_broken_by_input_order() -> None:
    r = Reranker("mock")
    res = r.rerank("alpha", ["alpha", "alpha"], top_k=2)
    assert [x.index for x in res] == [0, 1]


def test_rerank_cache_hit_avoids_re_score(monkeypatch: pytest.MonkeyPatch) -> None:
    r = Reranker("mock")
    counter = {"n": 0}
    original = r._impl._score_pairs

    def spy(query, docs):  # noqa: ANN001
        counter["n"] += 1
        return original(query, docs)

    monkeypatch.setattr(r._impl, "_score_pairs", spy, raising=False)
    docs = ["docA", "docB"]
    r.rerank("q", docs)
    r.rerank("q", docs)
    assert counter["n"] == 1


def test_rerank_cache_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rerank_cache_ttl_seconds", 0, raising=False)
    r = Reranker("mock")
    counter = {"n": 0}
    original = r._impl._score_pairs

    def spy(query, docs):  # noqa: ANN001
        counter["n"] += 1
        return original(query, docs)

    monkeypatch.setattr(r._impl, "_score_pairs", spy, raising=False)
    r.rerank("q", ["docX"])
    time.sleep(0.01)
    r.rerank("q", ["docX"])
    assert counter["n"] == 2


def test_rerank_cache_eviction_when_max_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rerank_cache_max_entries", 2, raising=False)
    monkeypatch.setattr(settings, "rerank_backend", "mock", raising=False)
    rr.close_reranker()
    r = rr.get_reranker()
    r.rerank("q1", ["a"])
    r.rerank("q2", ["b"])
    r.rerank("q3", ["c"])
    assert rr.cache_stats()["evictions"] >= 1


def test_get_reranker_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rerank_backend", "mock", raising=False)
    rr.close_reranker()
    a = rr.get_reranker()
    b = rr.get_reranker()
    assert a is b
    rr.close_reranker()
    c = rr.get_reranker()
    assert c is not a


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        Reranker("nope")


def test_qwen3_onnx_requires_model_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rerank_model_path", "", raising=False)
    with pytest.raises(ValueError):
        Reranker("qwen3_onnx")


def test_cohere_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)
    with pytest.raises(ValueError):
        Reranker("cohere")


def test_cache_stats_reflects_hits_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rerank_backend", "mock", raising=False)
    rr.close_reranker()
    r = rr.get_reranker()
    s0 = rr.cache_stats()
    assert s0["hits"] == 0 and s0["misses"] == 0 and s0["size"] == 0
    r.rerank("q", ["a", "b"])
    s1 = rr.cache_stats()
    assert s1["misses"] == 2
    assert s1["hits"] == 0
    assert s1["size"] == 2
    r.rerank("q", ["a", "b"])
    s2 = rr.cache_stats()
    assert s2["hits"] == 2
    assert s2["size"] == 2


def test_rerank_result_is_slots_dataclass() -> None:
    inst = RerankResult(index=0, score=1.0, doc="text")
    assert hasattr(RerankResult, "__slots__")
    with pytest.raises(AttributeError):
        inst.extra = 123  # type: ignore[attr-defined]
