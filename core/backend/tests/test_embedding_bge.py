"""BGE-M3 embedding service unit tests (mock backend)."""

from __future__ import annotations

import math

import pytest

from app.config import settings
from app.rag import embedding_bge as e
from app.rag.embedding_bge import BGEEmbedder, cosine


@pytest.fixture(autouse=True)
def _reset_singleton():
    e.close_embedder()
    yield
    e.close_embedder()


def test_cosine_identical_returns_one() -> None:
    assert cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_zero() -> None:
    assert cosine([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(0.0, abs=1e-9)


def test_cosine_zero_norm_returns_zero() -> None:
    assert cosine([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cosine([1, 2], [1, 2, 3])


def test_is_oom_detects_known_signatures() -> None:
    assert e._is_oom(RuntimeError("CUDA out of memory"))
    assert not e._is_oom(RuntimeError("not the moon"))
    assert e._is_oom(MemoryError("OOM here"))


def test_mock_backend_dim_default() -> None:
    assert BGEEmbedder("mock").dim == 1024


def test_mock_backend_returns_normalised_vectors() -> None:
    eb = BGEEmbedder("mock")
    vectors = eb.embed(["alpha", "beta"])
    assert len(vectors) == 2
    for vec in vectors:
        norm = math.sqrt(sum(v * v for v in vec))
        assert norm == pytest.approx(1.0, abs=1e-6)


def test_mock_backend_deterministic_and_distinct() -> None:
    eb = BGEEmbedder("mock")
    v1 = eb.embed(["abc"])[0]
    v2 = eb.embed(["abc"])[0]
    v3 = eb.embed(["def"])[0]
    assert v1 == v2
    assert v1 != v3


def test_mock_identical_strings_high_cosine() -> None:
    eb = BGEEmbedder("mock")
    a = eb.embed(["ABS RAG demo"])[0]
    b = eb.embed(["ABS RAG demo"])[0]
    c = eb.embed(["garbage 9c2 zxq"])[0]
    assert cosine(a, b) == pytest.approx(1.0, abs=1e-6)
    assert cosine(a, c) < 0.5


def test_embed_empty_list_returns_empty() -> None:
    assert BGEEmbedder("mock").embed([]) == []


def test_embed_one_empty_returns_zero_vector() -> None:
    eb = BGEEmbedder("mock")
    assert eb.embed_one("") == [0.0] * eb.dim


def test_embed_falls_back_under_simulated_oom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eb = BGEEmbedder("mock")
    call_counter = {"count": 0}
    original = eb._impl._embed_batch

    def flaky_batch(texts):  # noqa: ANN001
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise RuntimeError("CUDA out of memory")
        return original(texts)

    monkeypatch.setattr(eb._impl, "_embed_batch", flaky_batch)
    texts = [f"t{i}" for i in range(8)]
    result = eb.embed(texts)
    assert len(result) == 8
    assert call_counter["count"] >= 2


def test_embed_raises_when_oom_persists_at_min_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eb = BGEEmbedder("mock")
    monkeypatch.setattr(settings, "embedding_min_batch", 1, raising=False)
    monkeypatch.setattr(settings, "embedding_batch_size", 2, raising=False)

    def always_oom(_):  # noqa: ANN001
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(eb._impl, "_embed_batch", always_oom)
    with pytest.raises(RuntimeError):
        eb.embed(["x"] * 4)


def test_get_embedder_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "embedding_backend", "mock", raising=False)
    e.close_embedder()
    first = e.get_embedder()
    second = e.get_embedder()
    assert first is second
    e.close_embedder()
    third = e.get_embedder()
    assert third is not first


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        BGEEmbedder("nope")
