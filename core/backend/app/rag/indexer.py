"""RAG indexer — char-split chunk + ChromaDB persist + nomic embed.

Multi-tenant: her chunk metadata'sında `project` alanı; query tarafında filtre.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config import settings

from . import embedding as _emb
from .chunker import chunk_for_path

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "vendor",
    ".cache",
    ".pytest_cache",
}
_DEFAULT_EXTS = {
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".sh",
    ".css",
    ".html",
}
_CHUNK_CHARS = 1500


def _chroma_dir() -> Path:
    p = Path(settings.data_dir) / "rag_chroma"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _client():
    """ChromaDB persistent client (lazy import)."""
    import chromadb

    return chromadb.PersistentClient(path=str(_chroma_dir()))


def _collection(name: str = "abs_default"):
    return _client().get_or_create_collection(name=name)


def _hash_chunk(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _chunk_iter(text: str) -> Iterable[Tuple[int, str]]:
    for idx, start in enumerate(range(0, len(text), _CHUNK_CHARS)):
        yield idx, text[start : start + _CHUNK_CHARS]


def _walk_files(root: Path, extensions: Iterable[str]) -> Iterable[Path]:
    exts = {e.lower() for e in extensions}
    for dirpath, dirnames, filenames in os.walk(root):
        # in-place skip
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in exts:
                yield p


async def _embed_one(text: str) -> Optional[List[float]]:
    try:
        return await _emb.embed(text)
    except Exception as exc:
        logger.info("embed fail: %s", exc)
        return None


async def index_path(
    path: str,
    project: str = "default",
    extensions: Optional[List[str]] = None,
    chunk_strategy: str = "semantic",
) -> Dict[str, Any]:
    """Bir dosya/dizini chunk'la, embedding al, Chroma'ya yaz.

    chunk_strategy: "semantic" (default — AST/heading-aware) veya "char" (eski 1500 char split).
    """
    root = Path(path)
    if not root.exists():
        return {"error": f"yol yok: {path}", "indexed": 0, "skipped": 0}

    exts = list(extensions) if extensions else list(_DEFAULT_EXTS)
    files = [root] if root.is_file() else list(_walk_files(root, exts))

    coll = _collection()
    indexed = 0
    skipped = 0
    skipped_reasons: Dict[str, int] = {}

    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            skipped += 1
            skipped_reasons["read_fail"] = skipped_reasons.get("read_fail", 0) + 1
            continue
        if not text.strip():
            skipped += 1
            skipped_reasons["empty"] = skipped_reasons.get("empty", 0) + 1
            continue

        for idx, chunk in chunk_for_path(fp, text, chunk_strategy):
            doc_hash = _hash_chunk(chunk)
            doc_id = f"{project}:{fp}:{idx}:{doc_hash}"
            # Idempotency — aynı id varsa atla
            try:
                existing = coll.get(ids=[doc_id])
                if existing and existing.get("ids"):
                    skipped += 1
                    skipped_reasons["unchanged"] = skipped_reasons.get("unchanged", 0) + 1
                    continue
            except Exception:
                pass

            vec = await _embed_one(chunk)
            if not vec:
                skipped += 1
                skipped_reasons["embed_fail"] = skipped_reasons.get("embed_fail", 0) + 1
                continue

            try:
                coll.add(
                    ids=[doc_id],
                    documents=[chunk],
                    embeddings=[vec],
                    metadatas=[
                        {
                            "project": project,
                            "file": str(fp),
                            "chunk_idx": idx,
                            "hash": doc_hash,
                        }
                    ],
                )
                indexed += 1
            except Exception as exc:
                skipped += 1
                skipped_reasons["chroma_add"] = skipped_reasons.get("chroma_add", 0) + 1
                logger.info("chroma add fail: %s", exc)

    return {
        "project": project,
        "scanned_files": len(files),
        "indexed": indexed,
        "skipped": skipped,
        "skipped_reasons": skipped_reasons,
    }


def clear(project: Optional[str] = None) -> Dict[str, Any]:
    """Tüm collection veya yalnızca bir project metadata'lı chunk'ları sil."""
    coll = _collection()
    if project is None:
        try:
            count = coll.count()
            _client().delete_collection(name=coll.name)
        except Exception as exc:
            return {"error": str(exc)[:200], "deleted": 0}
        return {"deleted": count, "project": None}
    try:
        # Filter by metadata
        before = coll.count()
        coll.delete(where={"project": project})
        after = coll.count()
        return {"deleted": before - after, "project": project}
    except Exception as exc:
        return {"error": str(exc)[:200], "deleted": 0}
