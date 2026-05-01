"""Cohere alert pipeline — threshold + idempotency + ack + month reset."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.cohere import alert as ca
from app.config import settings


@pytest.fixture(autouse=True)
def _tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


def test_threshold_warn_fires_once_then_idempotent():
    assert ca.track_usage(count=800, limit=1000) == "warn"
    # Aynı ay, 81% — 'warn' tekrar tetiklenmemeli
    assert ca.track_usage(count=810, limit=1000) is None


def test_danger_then_limit_hit_progression():
    ca.track_usage(count=800, limit=1000)  # warn
    assert ca.track_usage(count=910, limit=1000) == "danger"
    assert ca.track_usage(count=1000, limit=1000) == "limit_hit"


def test_read_recent_returns_newest_first():
    ca.track_usage(count=800, limit=1000)
    ca.track_usage(count=900, limit=1000)
    recent = ca.read_recent(limit=5)
    assert len(recent) >= 2
    # En yeni önce
    assert recent[0]["level"] == "danger"
    assert recent[1]["level"] == "warn"


def test_mark_acknowledged_persists_to_file():
    ca.track_usage(count=800, limit=1000)
    recent = ca.read_recent(limit=1)
    aid = recent[0]["id"]
    assert ca.mark_acknowledged(aid) is True
    again = ca.read_recent(limit=1)
    assert again[0]["ack"] is True


def test_new_month_resets_counter(monkeypatch):
    ca.track_usage(count=900, limit=1000)
    snap = ca.usage_snapshot()
    assert snap["used_month"] == 900

    # Şimdiki ay'ı manuel değiştir → reset
    fake_month = "1999-12"
    monkeypatch.setattr(ca, "_current_month", lambda: fake_month)
    # Yeni ayda track_usage(count=10) → reset, count=10
    ca.track_usage(count=10, limit=1000)
    snap2 = ca.usage_snapshot(limit=1000)
    assert snap2["used_month"] == 10
    assert snap2["month"] == fake_month
