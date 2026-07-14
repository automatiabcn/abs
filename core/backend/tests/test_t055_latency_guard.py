"""Latency p95 guard tests."""

from __future__ import annotations

import pytest

from app.observability.latency_guard import LatencyGuard


def test_no_alert_below_minimum_sample_count() -> None:
    g = LatencyGuard(budget_ms=100.0, window=100)
    for _ in range(5):
        assert g.record(route="/v1/rag/query", latency_ms=10_000) is None


def test_alert_when_p95_exceeds_budget() -> None:
    g = LatencyGuard(budget_ms=50.0, window=100)
    for _ in range(60):
        g.record(route="/v1/rag/query", latency_ms=10.0)
    for _ in range(10):
        alert = g.record(route="/v1/rag/query", latency_ms=5000.0)
    assert alert is not None
    assert alert.p95_ms > 50.0


def test_route_isolation() -> None:
    g = LatencyGuard(budget_ms=50.0, window=100)
    for _ in range(60):
        g.record(route="/A", latency_ms=10.0)
    snapshot_a = g.snapshot("/A")
    snapshot_b = g.snapshot("/B")
    assert snapshot_a["sample_size"] == 60
    assert snapshot_b["sample_size"] == 0


def test_snapshot_returns_zero_for_empty_bucket() -> None:
    g = LatencyGuard()
    snap = g.snapshot("/never")
    assert snap["sample_size"] == 0
    assert snap["p95_ms"] == 0.0


def test_invalid_budget_raises() -> None:
    with pytest.raises(ValueError):
        LatencyGuard(budget_ms=0)


def test_invalid_window_raises() -> None:
    with pytest.raises(ValueError):
        LatencyGuard(window=0)


def test_record_requires_route() -> None:
    g = LatencyGuard()
    with pytest.raises(ValueError):
        g.record(route="", latency_ms=10.0)
