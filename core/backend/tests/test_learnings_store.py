"""Learnings JSONL store testleri."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def test_log_creates_jsonl_entry(isolated_data_dir):
    from app.learnings.store import log

    h = log("bugfix", "Çift refund webhook geldi → idempotency JTI lookup'la kapatıldı")
    assert h is not None
    file_path = isolated_data_dir / "learnings.jsonl"
    assert file_path.is_file()
    line = file_path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["category"] == "bugfix"
    assert parsed["hash"] == h
    assert parsed["source"] == "manual"


def test_log_idempotent_within_24h(isolated_data_dir):
    from app.learnings.store import log

    h1 = log("delegation", "ASK_KIMI ile yaptın - iyi karar")
    h2 = log("delegation", "ASK_KIMI ile yaptın - iyi karar")
    assert h1 is not None
    assert h2 is None  # dedup
    file_path = isolated_data_dir / "learnings.jsonl"
    lines = file_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_recent_count_window_days(isolated_data_dir):
    from app.learnings.store import recent_count

    file_path = isolated_data_dir / "learnings.jsonl"
    now = time.time()
    entries = [
        {"ts": now, "category": "bugfix", "lesson": "today", "hash": "h1"},
        {"ts": now - 5 * 86400, "category": "bugfix", "lesson": "5d ago", "hash": "h2"},
        {
            "ts": now - 35 * 86400,
            "category": "bugfix",
            "lesson": "35d ago",
            "hash": "h3",
        },
    ]
    file_path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )
    assert recent_count(window_days=30) == 2
    assert recent_count(window_days=7) == 2
    assert recent_count(window_days=3) == 1


def test_invalid_category_rejected(isolated_data_dir):
    from app.learnings.store import log

    h = log("foobar", "lesson with bad cat")
    assert h is None
    file_path = isolated_data_dir / "learnings.jsonl"
    assert not file_path.is_file()


def test_empty_lesson_rejected(isolated_data_dir):
    from app.learnings.store import log

    assert log("bugfix", "") is None
    assert log("bugfix", "   ") is None


def test_stats_reports_by_category(isolated_data_dir):
    from app.learnings.store import log, stats

    log("bugfix", "Lesson 1")
    log("delegation", "Lesson 2")
    log("delegation", "Lesson 3")
    s = stats()
    assert s["total"] == 3
    assert s["by_category"]["bugfix"] == 1
    assert s["by_category"]["delegation"] == 2
    assert s["last_30d"] == 3
