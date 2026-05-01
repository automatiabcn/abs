"""RAG query — Chroma cosine similarity + status."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

from . import embedding as _emb
from .indexer import _client, _collection


async def query(
    question: str,
    project_filter: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """En yakın N chunk'ı döner: file, snippet, score, project."""
    if not question.strip():
        return []
    try:
        vec = await _emb.embed(question)
    except Exception as exc:
        return [{"error": f"embed fail: {exc}"}]

    coll = _collection()
    where = {"project": project_filter} if project_filter else None
    try:
        result = coll.query(
            query_embeddings=[vec],
            n_results=max(1, min(top_k, 20)),
            where=where,
        )
    except Exception as exc:
        return [{"error": f"chroma query fail: {exc}"}]

    out: List[Dict[str, Any]] = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "file": (meta or {}).get("file"),
                "project": (meta or {}).get("project"),
                "chunk_idx": (meta or {}).get("chunk_idx"),
                "snippet": (doc or "")[:200],
                "score": round(1.0 - float(dist), 3) if dist is not None else None,
            }
        )
    return out


def status() -> Dict[str, Any]:
    """RAG koleksiyon durumu — total_chunks + db_size_mb."""
    try:
        client = _client()
        cols = client.list_collections()
        names = [c.name for c in cols]
        total = 0
        for c in cols:
            try:
                total += c.count()
            except Exception:
                continue
    except Exception as exc:
        return {"error": str(exc)[:200], "collections": [], "total_chunks": 0}

    chroma_dir = Path(settings.data_dir) / "rag_chroma"
    size_mb = 0.0
    if chroma_dir.is_dir():
        size_mb = round(
            sum(f.stat().st_size for f in chroma_dir.rglob("*") if f.is_file())
            / 1024
            / 1024,
            2,
        )
    return {
        "collections": names,
        "total_chunks": total,
        "db_size_mb": size_mb,
        "embedding_model": "nomic-embed-text",
        "chroma_dir": str(chroma_dir),
    }
