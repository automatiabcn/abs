# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-009 — Qdrant client wrapper enforcing payload-based multi-tenant isolation.

Every read/write demands a non-empty tenant_id; the public API surface keeps
direct unsafe queries impossible. Defense-in-depth on top of Cerbos pre-filter.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "TenantIsolationError",
    "close",
    "count",
    "delete_by_tenant",
    "ensure_collection",
    "get_qdrant",
    "search",
    "upsert_points",
]

_client: QdrantClient | None = None


class TenantIsolationError(RuntimeError):
    """Raised when a tenant boundary is violated (missing/empty/mismatched)."""


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        api_key = (settings.qdrant_api_key or "").strip() or None
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=api_key,
            prefer_grpc=False,
            timeout=5.0,
        )
        logger.debug("qdrant_client_init url=%s", settings.qdrant_url)
    return _client


def _require_tenant(tenant_id: str | None) -> str:
    if tenant_id is None:
        raise TenantIsolationError("tenant_id must be provided")
    stripped = tenant_id.strip()
    if not stripped:
        raise TenantIsolationError("tenant_id cannot be empty or whitespace")
    return stripped


def _tenant_filter(tenant_id: str, *, extra: Filter | None = None) -> Filter:
    must: list = [
        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
    ]
    if extra is not None and extra.must:
        must.extend(extra.must)
    should = list(extra.should) if extra is not None and extra.should else None
    must_not = list(extra.must_not) if extra is not None and extra.must_not else None
    return Filter(must=must, should=should, must_not=must_not)


_DISTANCE_MAP = {
    "Cosine": Distance.COSINE,
    "Dot": Distance.DOT,
    "Euclid": Distance.EUCLID,
}


def ensure_collection(
    name: str,
    *,
    vector_size: int | None = None,
    distance: str = "Cosine",
) -> None:
    client = get_qdrant()
    try:
        client.get_collection(collection_name=name)
        logger.debug("qdrant_collection_exists name=%s", name)
        return
    except Exception:
        pass

    size = int(vector_size or settings.qdrant_default_vector_size)
    dist = _DISTANCE_MAP.get(distance, Distance.COSINE)
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=size, distance=dist),
    )
    client.create_payload_index(
        collection_name=name,
        field_name="tenant_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=name,
        field_name="created_at",
        field_schema=PayloadSchemaType.INTEGER,
    )
    logger.info(
        "qdrant_collection_created name=%s size=%d distance=%s", name, size, distance
    )


def upsert_points(
    *,
    collection: str,
    tenant_id: str,
    points: list[PointStruct],
) -> int:
    tenant = _require_tenant(tenant_id)
    mismatched: list[Any] = []
    for pt in points:
        payload = dict(pt.payload or {})
        existing = payload.get("tenant_id")
        if existing is None:
            payload["tenant_id"] = tenant
            pt.payload = payload
        elif str(existing).strip() != tenant:
            mismatched.append(pt.id)
    if mismatched:
        raise TenantIsolationError(
            f"tenant mismatch on points={mismatched} tenant={tenant}"
        )

    client = get_qdrant()
    client.upsert(collection_name=collection, points=points, wait=True)
    logger.info(
        "qdrant_upsert collection=%s tenant=%s n=%d", collection, tenant, len(points)
    )
    return len(points)


def search(
    *,
    collection: str,
    tenant_id: str,
    query_vector: list[float],
    limit: int = 10,
    score_threshold: float | None = None,
    extra_filter: Filter | None = None,
) -> list[dict[str, Any]]:
    tenant = _require_tenant(tenant_id)
    client = get_qdrant()
    if hasattr(client, "query_points"):
        # qdrant-client >= 1.13 removed `search`; `query_points` is the
        # canonical replacement and returns a QueryResponse with `.points`.
        response = client.query_points(
            collection_name=collection,
            query=list(query_vector),
            limit=limit,
            score_threshold=score_threshold,
            query_filter=_tenant_filter(tenant, extra=extra_filter),
        )
        hits = list(response.points)
    else:  # pragma: no cover — legacy SDK fallback
        hits = client.search(  # type: ignore[attr-defined]
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=_tenant_filter(tenant, extra=extra_filter),
        )
    return [
        {
            "id": str(p.id),
            "score": float(p.score),
            "payload": dict(p.payload or {}),
        }
        for p in hits
    ]


def delete_by_tenant(
    *,
    collection: str,
    tenant_id: str,
    point_ids: list[str | int] | None = None,
) -> int:
    tenant = _require_tenant(tenant_id)
    client = get_qdrant()

    if point_ids is not None:
        tenant_filter = _tenant_filter(tenant)
        owned: set[Any] = set()
        scroll_offset = None
        while True:
            batch, scroll_offset = client.scroll(
                collection_name=collection,
                scroll_filter=tenant_filter,
                limit=1000,
                offset=scroll_offset,
                with_payload=False,
                with_vectors=False,
            )
            owned.update(p.id for p in batch)
            if not scroll_offset:
                break

        missing = [pid for pid in point_ids if pid not in owned]
        if missing:
            raise TenantIsolationError(
                f"delete refused — points not in tenant={tenant}: {missing}"
            )

        client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=list(point_ids)),
            wait=True,
        )
        logger.info(
            "qdrant_delete_ids collection=%s tenant=%s n=%d",
            collection,
            tenant,
            len(point_ids),
        )
        return len(point_ids)

    pre = client.count(
        collection_name=collection,
        count_filter=_tenant_filter(tenant),
        exact=True,
    ).count
    client.delete(
        collection_name=collection,
        points_selector=FilterSelector(filter=_tenant_filter(tenant)),
        wait=True,
    )
    logger.info(
        "qdrant_delete_bulk collection=%s tenant=%s n=%d", collection, tenant, pre
    )
    return int(pre)


def count(*, collection: str, tenant_id: str) -> int:
    tenant = _require_tenant(tenant_id)
    client = get_qdrant()
    return int(
        client.count(
            collection_name=collection,
            count_filter=_tenant_filter(tenant),
            exact=True,
        ).count
    )


def close() -> None:
    global _client
    if _client is None:
        return
    try:
        _client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_close_error: %s", exc)
    finally:
        _client = None
