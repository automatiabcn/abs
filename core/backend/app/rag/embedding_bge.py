# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""BGE-M3 dense embedding service for the RAG pipeline."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "BGEEmbedder",
    "close_embedder",
    "cosine",
    "get_embedder",
]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must be the same length")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


_OOM_MARKERS = (
    "out of memory",
    "oom",
    "cuda error",
    "device-side assert",
    "cublas",
)


def _is_oom(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _OOM_MARKERS)


class _MockBackend:
    """Pure-stdlib deterministic backend used by tests + offline dev."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        # Loud, not INFO: with the mock backend RAG semantic search does NOT
        # work. Vectors are sha256-derived, so only byte-identical text matches;
        # semantically similar queries return effectively-random rankings. This
        # must be visible in every deployment that left ABS_EMBEDDING_BACKEND at
        # its default rather than reading as a normal startup line.
        logger.warning(
            "embedding backend=mock — RAG semantic retrieval is NON-FUNCTIONAL "
            "(sha256 vectors match only identical text). Set "
            "ABS_EMBEDDING_BACKEND=sentence_transformers (pip install "
            "sentence-transformers) or =ollama (bge-m3) for real search. dim=%d",
            dim,
        )

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for txt in texts:
            digest = hashlib.sha256(txt.encode("utf-8")).digest()
            repeats = (self.dim + len(digest) - 1) // len(digest)
            raw = (digest * repeats)[: self.dim]
            vec = [(b / 127.5) - 1.0 for b in raw]
            norm = math.sqrt(sum(v * v for v in vec))
            if norm == 0.0:
                out.append([0.0] * self.dim)
            else:
                out.append([v / norm for v in vec])
        return out

    def close(self) -> None:
        return None


class _CohereBackend:
    """Cloud embeddings via the customer's Cohere key — bring-your-own-key,
    zero local footprint, no model download, no GPU.

    ``embed-multilingual-v3.0`` is 1024-dim, matching ``qdrant_default_vector_size``
    and the bge-m3 default, so switching to it needs no collection migration.
    The Cohere SDK client is async; ``/v1/rag/*`` routes are sync (FastAPI runs
    them in a threadpool), so there is no running event loop and ``asyncio.run``
    is safe here.

    This is the recommended real backend for self-host: customers already
    provide a Cohere key for the model cascade, so RAG works with one env var
    (``ABS_EMBEDDING_BACKEND=cohere``) and zero extra footprint.
    """

    def __init__(self, model: str | None = None) -> None:
        if not (getattr(settings, "cohere_api_key", "") or ""):
            raise ValueError("embedding_backend=cohere requires ABS_COHERE_API_KEY")
        try:
            import cohere  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "embedding_backend=cohere requires the 'cohere' package"
            ) from exc
        self.model = model or getattr(
            settings, "cohere_embed_model", "embed-multilingual-v3.0"
        )
        self.dim = 1024
        logger.info("embedding_cohere_init model=%s dim=1024", self.model)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        import cohere

        async def _run() -> list[list[float]]:
            client = cohere.AsyncClientV2(api_key=settings.cohere_api_key, timeout=30.0)
            resp = await client.embed(
                texts=[t[:8000] for t in texts],
                model=self.model,
                input_type="search_document",
                embedding_types=["float"],
            )
            floats = (
                getattr(resp.embeddings, "float", None)
                or getattr(resp.embeddings, "float_", None)
                or []
            )
            return [list(v) for v in floats]

        return asyncio.run(_run())

    def close(self) -> None:
        return None


class _OllamaBackend:
    """Local embeddings via Ollama (bge-m3 by default).

    This backend was documented in `ABS_EMBEDDING_BACKEND`'s own comment, named
    in the mock's "set this for real search" warning — and was not a branch in
    this class, which is the one both ingest and chat go through. Anybody who
    followed that advice got `ValueError: unsupported embedding backend: ollama`
    on their first upload. It exists now.

    bge-m3 is 1024-dim, matching `qdrant_default_vector_size`, so no collection
    migration is needed. The dimension is read from the model rather than
    assumed, because a deployment that points `ABS_EMBEDDING_MODEL` at
    nomic-embed-text (768) must fail loudly at collection creation instead of
    writing mis-shaped vectors.
    """

    def __init__(self, model: str | None = None) -> None:
        import httpx

        self.model = model or getattr(settings, "embedding_model", "") or "bge-m3"
        self.url = (
            getattr(settings, "ollama_url", "") or "http://localhost:11434"
        ).rstrip("/")
        self._client = httpx.Client(timeout=60.0)
        self.dim = len(self._embed_batch(["dimension probe"])[0])
        logger.info(
            "embedding_ollama_init model=%s url=%s dim=%d",
            self.model,
            self.url,
            self.dim,
        )

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            resp = self._client.post(
                f"{self.url}/api/embeddings",
                json={"model": self.model, "prompt": text[:8000]},
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"ollama embed {resp.status_code}: {resp.text[:200]}"
                )
            vec = resp.json().get("embedding") or []
            if not vec:
                raise RuntimeError("ollama embed returned an empty vector")
            norm = math.sqrt(sum(v * v for v in vec))
            out.append([v / norm for v in vec] if norm else list(vec))
        return out

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass


class _SentenceTransformersBackend:
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for the 'sentence_transformers' "
                "backend. Install with `pip install sentence-transformers`."
            ) from exc

        self.model = SentenceTransformer(model_name, device=device)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        logger.info(
            "embedding_sentence_transformers_init model=%s device=%s dim=%d",
            model_name,
            device,
            self.dim,
        )

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return embeddings.tolist()

    def close(self) -> None:
        return None


class _OnnxBackend:
    def __init__(self, model_path: str, providers: list[str]) -> None:
        if not model_path:
            raise ValueError("embedding_model_path must be set for the ONNX backend")
        try:
            import onnxruntime as ort  # noqa: F401
            from transformers import AutoTokenizer  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "onnxruntime and transformers are required for the ONNX backend. "
                "Install with `pip install onnxruntime[-gpu] transformers`."
            ) from exc

        import onnxruntime as ort
        from transformers import AutoTokenizer

        self.session = ort.InferenceSession(model_path, providers=providers)
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        try:
            shape = self.session.get_outputs()[0].shape
            tail = shape[-1] if isinstance(shape, (list, tuple)) and shape else None
            self.dim = int(tail) if isinstance(tail, int) and tail > 0 else 1024
        except Exception:
            self.dim = 1024
        logger.info("embedding_onnx_init providers=%s dim=%d", providers, self.dim)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        enc = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="np",
        )
        outputs = self.session.run(
            None,
            {
                "input_ids": enc["input_ids"],
                "attention_mask": enc["attention_mask"],
            },
        )
        last_hidden = outputs[0]
        mask = enc["attention_mask"][:, :, None]
        masked = last_hidden * mask
        summed = masked.sum(axis=1)
        lengths = mask.sum(axis=1)
        lengths = np.where(lengths == 0, 1, lengths)
        mean = summed / lengths
        norms = np.linalg.norm(mean, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return (mean / norms).tolist()

    def close(self) -> None:
        return None


def _ollama_serves_embeddings() -> bool:
    """True when a local Ollama is up and has the embedding model pulled."""
    import httpx

    wanted = (getattr(settings, "embedding_model", "") or "bge-m3").split(":")[0]
    url = (getattr(settings, "ollama_url", "") or "http://localhost:11434").rstrip("/")
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=2.0)
        if resp.status_code >= 400:
            return False
        names = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:  # noqa: BLE001 — absence of Ollama is the normal case
        return False
    return any(n.split(":")[0] == wanted for n in names)


def resolve_backend(configured: str) -> str:
    """Pick a real embedding backend when the operator has not named one.

    The old default was `mock`, and mock is not a degraded mode — it is sha256
    of the text. Semantically similar queries land nowhere near each other, so
    "chat with your documents" returned a random five chunks and the model
    answered confidently from them. Nothing failed, nothing 500'd; the answers
    were just quietly sourced from the wrong documents. A warning in the log is
    not a defence against that, because the person it is warning does not read
    the log.

    So the default resolves to whatever real backend the box can actually run,
    local first: an embedding sends every document a customer owns to whoever
    computes the vector, and that is not a thing to opt somebody into silently.
    Cloud (their own Cohere key) only when there is no local option. Mock is
    reachable only by asking for it by name, which is what the test suite does.
    """
    name = (configured or "").strip().lower()
    if name and name != "auto":
        return name
    if _ollama_serves_embeddings():
        return "ollama"
    try:
        import sentence_transformers  # noqa: F401

        return "sentence_transformers"
    except ImportError:
        pass
    if getattr(settings, "cohere_api_key", "") or "":
        return "cohere"
    # Nothing real is available. The old code fell back to `mock` here — sha256
    # vectors — which is how "chat with your documents" came to answer confidently
    # from five unrelated chunks with every light green. The docstring above already
    # said mock was reachable only by name; the code disagreed with it.
    #
    # `none` refuses to embed at all. That is the whole point: a search that cannot
    # work must fail where it is called, not return something that looks like an
    # answer. Indexing fails loudly too, which is correct — a corpus embedded by
    # nothing is not a corpus.
    logger.error(
        "no embedding backend available — document search is disabled. Install "
        "Ollama and `ollama pull bge-m3`, `pip install sentence-transformers`, or "
        "set ABS_COHERE_API_KEY. (ABS_EMBEDDING_BACKEND=mock is for tests and "
        "produces meaningless results.)"
    )
    return "none"


class EmbeddingUnavailable(RuntimeError):
    """No embedding model is configured, so nothing can be embedded or searched.

    Raised rather than returning a vector, because every alternative to raising is
    a lie: a zero vector, a random one, or a hash all produce a search that returns
    *something*, and something is what the customer will read as an answer.
    """


class _NoneBackend:
    """The absence of an embedding model, made explicit and made loud."""

    dim = 1024
    model = ""

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailable(
            "no embedding model is configured — documents cannot be indexed or "
            "searched. Set ABS_EMBEDDING_BACKEND (ollama / sentence_transformers / "
            "cohere)."
        )

    # The backends are duck-typed and the callers are not consistent about which
    # name they reach for. Every door leads to the same refusal, so none of them
    # can quietly become the one that returns a vector.
    encode = _embed_batch
    embed = _embed_batch
    __call__ = _embed_batch


class BGEEmbedder:
    backend: str
    dim: int
    semantic: bool
    _impl: Any

    def __init__(self, backend: str) -> None:
        self.backend = backend
        # Whether this backend actually understands meaning. Retrieval refuses to
        # answer from a backend that does not, rather than dressing up hash
        # collisions as citations. `none` is the honest absence of one; `mock` is a
        # test fixture that must never be reached by resolution, only by name.
        self.semantic = backend not in ("mock", "none")
        if backend == "none":
            self._impl = _NoneBackend()
        elif backend == "mock":
            self._impl = _MockBackend()
        elif backend == "cohere":
            self._impl = _CohereBackend()
        elif backend == "ollama":
            self._impl = _OllamaBackend()
        elif backend == "sentence_transformers":
            self._impl = _SentenceTransformersBackend(
                model_name="BAAI/bge-m3",
                device=getattr(settings, "embedding_device", "cpu"),
            )
        elif backend == "onnx_cuda":
            self._impl = _OnnxBackend(
                model_path=getattr(settings, "embedding_model_path", ""),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
        elif backend == "onnx_cpu":
            self._impl = _OnnxBackend(
                model_path=getattr(settings, "embedding_model_path", ""),
                providers=["CPUExecutionProvider"],
            )
        else:
            raise ValueError(f"unsupported embedding backend: {backend}")
        self.dim = int(getattr(self._impl, "dim", 1024))

    def model_id(self) -> str:
        """Identity of the model that produced a vector, stamped onto chunks.

        Two vectors are only comparable when the same model made them. Written
        into every chunk's payload so a corpus embedded by a previous backend
        can be recognised as stale rather than silently searched against.
        """
        name = getattr(self._impl, "model", "") or getattr(self._impl, "model_name", "")
        return f"{self.backend}:{name}" if name else self.backend

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        batch_size = max(1, int(getattr(settings, "embedding_batch_size", 32)))
        min_batch = max(1, int(getattr(settings, "embedding_min_batch", 4)))

        i = 0
        while i < len(texts):
            chunk = texts[i : i + batch_size]
            try:
                results.extend(self._impl._embed_batch(chunk))
                i += len(chunk)
                continue
            except (MemoryError, RuntimeError) as exc:
                if not _is_oom(exc):
                    raise
                if batch_size <= min_batch:
                    logger.error(
                        "embedding_oom_at_min batch=%d msg=%s", batch_size, exc
                    )
                    raise
                old = batch_size
                batch_size = max(batch_size // 2, min_batch)
                logger.warning("embedding_oom_reduce from=%d to=%d", old, batch_size)
        return results

    def embed_one(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dim
        return self.embed([text])[0]

    def close(self) -> None:
        try:
            self._impl.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedder_close_error: %s", exc)


_embedder: BGEEmbedder | None = None


def get_embedder() -> BGEEmbedder:
    global _embedder
    if _embedder is None:
        backend = resolve_backend(getattr(settings, "embedding_backend", "auto"))
        _embedder = BGEEmbedder(backend)
        logger.info(
            "embedder_singleton_init backend=%s dim=%d semantic=%s",
            backend,
            _embedder.dim,
            _embedder.semantic,
        )
    return _embedder


def model_id_of(embedder: Any) -> str:
    """The identity stamp for whatever embedder a caller happens to hold.

    The ingest paths accept an injected embedder (tests, and the asyncio wrapper
    the file-ingest route uses), and not all of them are a `BGEEmbedder`. A
    missing `model_id` must degrade to an unknown stamp, not a 500 in the middle
    of somebody's upload.
    """
    fn = getattr(embedder, "model_id", None)
    if callable(fn):
        try:
            return str(fn() or "unknown")
        except Exception:  # noqa: BLE001
            return "unknown"
    return str(getattr(embedder, "backend", "") or "unknown")


def close_embedder() -> None:
    global _embedder
    if _embedder is None:
        return
    try:
        _embedder.close()
    finally:
        _embedder = None
