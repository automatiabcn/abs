"""T-009 — Qdrant client wrapper unit tests (no live broker)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("qdrant_client")

from qdrant_client.models import (  # noqa: E402
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config import settings  # noqa: E402
from app.rag import qdrant_client as qc  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qc, "_client", None, raising=False)


def _has_tenant_match(filt: Filter, value: str) -> bool:
    return any(
        isinstance(c, FieldCondition)
        and c.key == "tenant_id"
        and isinstance(c.match, MatchValue)
        and c.match.value == value
        for c in (filt.must or [])
    )


def test_require_tenant_rejects_none_and_empty() -> None:
    with pytest.raises(qc.TenantIsolationError):
        qc._require_tenant(None)
    with pytest.raises(qc.TenantIsolationError):
        qc._require_tenant("")
    with pytest.raises(qc.TenantIsolationError):
        qc._require_tenant("   ")
    assert qc._require_tenant("t1  ") == "t1"


def test_tenant_filter_always_includes_tenant_condition() -> None:
    f = qc._tenant_filter("t1")
    assert isinstance(f, Filter)
    assert _has_tenant_match(f, "t1")
    assert len(f.must or []) == 1


def test_tenant_filter_merges_extra_must_conditions() -> None:
    extra = Filter(must=[FieldCondition(key="lang", match=MatchValue(value="tr"))])
    f = qc._tenant_filter("t1", extra=extra)
    keys = {c.key for c in (f.must or [])}
    assert keys == {"tenant_id", "lang"}


def test_ensure_collection_creates_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.get_collection.side_effect = Exception("missing")
    monkeypatch.setattr(qc, "_client", client, raising=False)

    qc.ensure_collection("mycol")
    client.create_collection.assert_called_once()
    cfg = client.create_collection.call_args.kwargs["vectors_config"]
    assert isinstance(cfg, VectorParams)
    assert cfg.size == settings.qdrant_default_vector_size
    assert cfg.distance == Distance.COSINE
    assert client.create_payload_index.call_count == 2
    fields = [
        c.kwargs["field_name"] for c in client.create_payload_index.call_args_list
    ]
    assert fields == ["tenant_id", "created_at"]


def test_ensure_collection_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.get_collection.return_value = SimpleNamespace(name="mycol")
    monkeypatch.setattr(qc, "_client", client, raising=False)

    qc.ensure_collection("mycol")
    client.create_collection.assert_not_called()
    client.create_payload_index.assert_not_called()


def test_ensure_collection_distance_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.get_collection.side_effect = Exception("missing")
    monkeypatch.setattr(qc, "_client", client, raising=False)

    qc.ensure_collection("dotcol", distance="Dot")
    cfg = client.create_collection.call_args.kwargs["vectors_config"]
    assert cfg.distance == Distance.DOT


def test_upsert_injects_missing_tenant_id_into_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(qc, "_client", client, raising=False)

    pt = PointStruct(id=1, vector=[0.1] * 4, payload={})
    n = qc.upsert_points(collection="c", tenant_id="t1", points=[pt])
    assert n == 1
    sent = client.upsert.call_args.kwargs["points"]
    assert sent[0].payload["tenant_id"] == "t1"


def test_upsert_raises_on_tenant_mismatch_lists_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(qc, "_client", client, raising=False)

    pt = PointStruct(id=2, vector=[0.2] * 4, payload={"tenant_id": "other"})
    with pytest.raises(qc.TenantIsolationError) as exc:
        qc.upsert_points(collection="c", tenant_id="t1", points=[pt])
    assert "2" in str(exc.value)
    client.upsert.assert_not_called()


def test_search_passes_tenant_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(id="p1", score=0.9, payload={"tenant_id": "t1"})]
    )
    monkeypatch.setattr(qc, "_client", client, raising=False)

    out = qc.search(collection="c", tenant_id="t1", query_vector=[0.1] * 4, limit=5)
    kwargs = client.query_points.call_args.kwargs
    assert _has_tenant_match(kwargs["query_filter"], "t1")
    assert kwargs["limit"] == 5
    assert kwargs["query"] == [0.1, 0.1, 0.1, 0.1]
    assert out == [{"id": "p1", "score": 0.9, "payload": {"tenant_id": "t1"}}]


def test_search_requires_tenant() -> None:
    with pytest.raises(qc.TenantIsolationError):
        qc.search(collection="c", tenant_id="", query_vector=[0.1])


def test_count_uses_tenant_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.count.return_value = SimpleNamespace(count=42)
    monkeypatch.setattr(qc, "_client", client, raising=False)

    assert qc.count(collection="c", tenant_id="t1") == 42
    assert _has_tenant_match(client.count.call_args.kwargs["count_filter"], "t1")


def test_delete_by_tenant_with_ids_verifies_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.scroll.return_value = ([SimpleNamespace(id=1)], None)
    monkeypatch.setattr(qc, "_client", client, raising=False)

    with pytest.raises(qc.TenantIsolationError) as exc:
        qc.delete_by_tenant(collection="c", tenant_id="t1", point_ids=[1, 99])
    assert "99" in str(exc.value)
    client.delete.assert_not_called()


def test_delete_by_tenant_with_ids_succeeds_when_all_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.scroll.return_value = (
        [SimpleNamespace(id=1), SimpleNamespace(id=2)],
        None,
    )
    monkeypatch.setattr(qc, "_client", client, raising=False)

    n = qc.delete_by_tenant(collection="c", tenant_id="t1", point_ids=[1, 2])
    assert n == 2
    selector = client.delete.call_args.kwargs["points_selector"]
    assert isinstance(selector, PointIdsList)
    assert list(selector.points) == [1, 2]


def test_delete_by_tenant_bulk_uses_filter_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.count.return_value = SimpleNamespace(count=10)
    monkeypatch.setattr(qc, "_client", client, raising=False)

    n = qc.delete_by_tenant(collection="c", tenant_id="t1", point_ids=None)
    assert n == 10
    selector = client.delete.call_args.kwargs["points_selector"]
    assert isinstance(selector, FilterSelector)
    assert _has_tenant_match(selector.filter, "t1")


def test_close_resets_singleton_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(qc, "_client", client, raising=False)

    qc.close()
    client.close.assert_called_once()
    assert qc._client is None

    qc.close()
    assert client.close.call_count == 1
