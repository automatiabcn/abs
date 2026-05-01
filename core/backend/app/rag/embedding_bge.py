"""T-010 — BGE-M3 dense embedding service for the RAG pipeline."""

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
        logger.info("embedding_mock_init dim=%d", dim)

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
            raise ValueError(
                "embedding_model_path must be set for the ONNX backend"
            )
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
        logger.info(
            "embedding_onnx_init providers=%s dim=%d", providers, self.dim
        )

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


class BGEEmbedder:
    backend: str
    dim: int
    _impl: Any

    def __init__(self, backend: str) -> None:
        self.backend = backend
        if backend == "mock":
            self._impl = _MockBackend()
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
                logger.warning(
                    "embedding_oom_reduce from=%d to=%d", old, batch_size
                )
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
        backend = getattr(settings, "embedding_backend", "mock") or "mock"
        _embedder = BGEEmbedder(backend)
        logger.info(
            "embedder_singleton_init backend=%s dim=%d", backend, _embedder.dim
        )
    return _embedder


def close_embedder() -> None:
    global _embedder
    if _embedder is None:
        return
    try:
        _embedder.close()
    finally:
        _embedder = None
