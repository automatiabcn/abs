# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Meeting upload → RAG auto-index wiring (Step 4).

A finished transcript must be best-effort indexed into the tenant's Qdrant
document store (settings.qdrant_default_collection) under the same tenant the
panel RAG ingest resolves — so meetings are answerable from panel search +
MCP rag_query. A RAG/Qdrant failure must NOT fail the upload.
"""

from __future__ import annotations

import pytest

from app.api import meetings as meetings_mod


def test_autoindex_uses_default_collection_and_resolved_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(
        settings, "qdrant_default_collection", "abs_documents", raising=False
    )
    monkeypatch.setattr("app.api.chat._resolve_tenant", lambda email: "acme")

    class _Emb:
        dim = 1024

        def embed(self, texts):
            return [[0.05] * self.dim for _ in texts]

        def model_id(self):
            # Stamped onto every chunk: vectors are only comparable to others
            # from the same model, so the chunk has to say which one made it.
            return "ollama:bge-m3"

    monkeypatch.setattr("app.rag.embedding_bge.get_embedder", lambda: _Emb())

    captured: dict = {}

    def _ensure(name, vector_size=None):
        captured["ensure"] = (name, vector_size)

    def _upsert(*, collection, tenant_id, points):
        captured["collection"] = collection
        captured["tenant_id"] = tenant_id
        captured["points"] = points
        return len(points)

    monkeypatch.setattr("app.rag.qdrant_client.ensure_collection", _ensure)
    monkeypatch.setattr("app.rag.qdrant_client.upsert_points", _upsert)

    result = {
        "language": "tr",
        "duration_sec": 12.0,
        "backend": "mock",
        "segments": [
            {"speaker_id": "S1", "start": 0.0, "end": 6.0, "text": "kira her ayın 5'i"},
            {"speaker_id": "S2", "start": 6.0, "end": 12.0, "text": "tamam not aldım"},
        ],
    }
    n = meetings_mod._autoindex_meeting_rag(
        meeting_id=42, title="sync.mp3", uploader_email="admin@acme", result=result
    )

    assert n == 2
    assert captured["collection"] == "abs_documents"
    assert captured["tenant_id"] == "acme"
    pt = captured["points"][0]
    # PointStruct id must be a UUID (not the raw `meeting-42-seg-0000` chunk id).
    import uuid

    uuid.UUID(str(pt.id))  # raises if not a valid UUID
    assert pt.payload["tenant_id"] == "acme"
    assert pt.payload["kind"] == "meeting_transcript"
    assert pt.payload["doc_id"] == "meeting-42"
    assert "kira" in pt.payload["text"]
