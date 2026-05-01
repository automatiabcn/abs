"""T-009 — Qdrant live integration: cross-tenant isolation gate."""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

pytest.importorskip("qdrant_client")

from qdrant_client.models import PointStruct  # noqa: E402

from app.config import settings  # noqa: E402
from app.rag import qdrant_client as qc  # noqa: E402

QDRANT_URL = os.environ.get("ABS_QDRANT_URL", "http://127.0.0.1:6333")


def _broker_reachable() -> bool:
    try:
        r = httpx.get(f"{QDRANT_URL}/readyz", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _require_qdrant():
    if not _broker_reachable():
        pytest.skip(f"Qdrant not reachable at {QDRANT_URL}")
    settings.qdrant_url = QDRANT_URL
    qc.close()
    yield
    qc.close()


@pytest.fixture()
def collection() -> str:
    name = f"abs_iso_{uuid.uuid4().hex[:8]}"
    qc.ensure_collection(name, vector_size=4)
    yield name
    try:
        qc.get_qdrant().delete_collection(collection_name=name)
    except Exception:
        pass


def test_cross_tenant_search_returns_zero_results(collection: str) -> None:
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-A",
        points=[
            PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4], payload={"doc": "A1"}),
            PointStruct(id=2, vector=[0.1, 0.2, 0.3, 0.5], payload={"doc": "A2"}),
        ],
    )
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-B",
        points=[
            PointStruct(id=10, vector=[0.9, 0.8, 0.7, 0.6], payload={"doc": "B1"}),
        ],
    )

    a_results = qc.search(
        collection=collection,
        tenant_id="tenant-A",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=10,
    )
    assert len(a_results) == 2
    assert all(h["payload"]["tenant_id"] == "tenant-A" for h in a_results)

    b_results_with_a_vector = qc.search(
        collection=collection,
        tenant_id="tenant-B",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=10,
    )
    assert all(h["payload"]["tenant_id"] == "tenant-B" for h in b_results_with_a_vector)
    assert len(b_results_with_a_vector) == 1


def test_count_per_tenant_isolated(collection: str) -> None:
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-A",
        points=[
            PointStruct(id=1, vector=[0.1] * 4, payload={}),
            PointStruct(id=2, vector=[0.2] * 4, payload={}),
            PointStruct(id=3, vector=[0.3] * 4, payload={}),
        ],
    )
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-B",
        points=[PointStruct(id=10, vector=[0.9] * 4, payload={})],
    )

    assert qc.count(collection=collection, tenant_id="tenant-A") == 3
    assert qc.count(collection=collection, tenant_id="tenant-B") == 1
    assert qc.count(collection=collection, tenant_id="tenant-ghost") == 0


def test_delete_with_other_tenant_ids_refused(collection: str) -> None:
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-A",
        points=[PointStruct(id=1, vector=[0.1] * 4, payload={})],
    )
    qc.upsert_points(
        collection=collection,
        tenant_id="tenant-B",
        points=[PointStruct(id=10, vector=[0.5] * 4, payload={})],
    )

    with pytest.raises(qc.TenantIsolationError):
        qc.delete_by_tenant(
            collection=collection, tenant_id="tenant-A", point_ids=[1, 10]
        )

    assert qc.count(collection=collection, tenant_id="tenant-B") == 1


def test_search_p95_latency_under_150ms(collection: str) -> None:
    points = [
        PointStruct(
            id=i,
            vector=[(i % 7) / 10, (i % 11) / 10, (i % 13) / 10, (i % 17) / 10],
            payload={"i": i},
        )
        for i in range(500)
    ]
    qc.upsert_points(collection=collection, tenant_id="tenant-perf", points=points)

    samples_ms: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        qc.search(
            collection=collection,
            tenant_id="tenant-perf",
            query_vector=[0.1, 0.2, 0.3, 0.4],
            limit=5,
        )
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    samples_ms.sort()
    p95 = samples_ms[int(0.95 * len(samples_ms))]
    print(f"\n[T-009] qdrant search p50={samples_ms[49]:.2f}ms p95={p95:.2f}ms")
    assert p95 < 150.0, f"p95 {p95:.2f}ms exceeds 150ms budget"
