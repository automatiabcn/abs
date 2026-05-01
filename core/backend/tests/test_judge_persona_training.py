"""010 — Judge persona live training testleri (fake JSONL)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_persona_dirs(monkeypatch, tmp_path: Path):
    """data_dir + cache_dir tmp dizinlere yönlendir, judge_log + persona izole."""
    from app.config import settings

    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    data_dir.mkdir()
    cache_dir.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data_dir))
    monkeypatch.setattr(settings, "cache_dir", str(cache_dir))
    return {"data": data_dir, "cache": cache_dir}


def _write_judge_log(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _entry(outcome: str, drift: float) -> dict:
    return {
        "id": f"id-{outcome}-{drift}",
        "ts": time.time(),
        "source": "test",
        "ast_score": 7.5,
        "llm_score": 8.0,
        "combined_score": 7.7,
        "persona_drift": drift,
        "outcome": outcome,
    }


def test_persona_train_insufficient_data(isolated_persona_dirs):
    from app.judge.persona import DEFAULT_PERSONA, load_persona
    from app.judge.training import train_persona

    res = train_persona(min_samples=10)
    assert res["action"] == "insufficient_data"
    assert res["samples"] == 0
    assert load_persona() == DEFAULT_PERSONA


def test_persona_train_loosens_when_rejects_have_higher_drift(isolated_persona_dirs):
    from app.judge.persona import load_persona
    from app.judge.training import train_persona

    log_path = isolated_persona_dirs["data"] / "judge_log.jsonl"
    entries = [_entry("accept", 0.10) for _ in range(5)] + [
        _entry("reject", 0.30) for _ in range(5)
    ]
    _write_judge_log(log_path, entries)

    res = train_persona(min_samples=10)
    assert res["action"] == "loosen"
    assert res["samples"] == 10
    assert res["accept_drift_avg"] == pytest.approx(0.10, abs=1e-4)
    assert res["reject_drift_avg"] == pytest.approx(0.30, abs=1e-4)
    assert res["after"]["docstring_ratio"] == pytest.approx(0.55, abs=1e-4)
    assert res["after"]["type_hints_ratio"] == pytest.approx(0.65, abs=1e-4)
    persisted = load_persona()
    assert persisted["docstring_ratio"] == pytest.approx(0.55, abs=1e-4)


def test_persona_train_tightens_when_accepts_have_lower_drift(isolated_persona_dirs):
    from app.judge.training import train_persona

    log_path = isolated_persona_dirs["data"] / "judge_log.jsonl"
    entries = [_entry("accept", 0.05) for _ in range(5)] + [
        _entry("reject", 0.20) for _ in range(5)
    ]
    # accept_avg=0.05, reject_avg=0.20 → delta = +0.15 → loosen
    # Tightens için tersi: accept yüksek drift, reject düşük drift
    entries = [_entry("accept", 0.30) for _ in range(5)] + [
        _entry("reject", 0.05) for _ in range(5)
    ]
    _write_judge_log(log_path, entries)

    res = train_persona(min_samples=10)
    assert res["action"] == "tighten"
    assert res["after"]["docstring_ratio"] == pytest.approx(0.65, abs=1e-4)
    assert res["after"]["type_hints_ratio"] == pytest.approx(0.75, abs=1e-4)


def test_persona_reset_restores_default(isolated_persona_dirs):
    from app.judge.persona import DEFAULT_PERSONA, load_persona
    from app.judge.training import reset_persona, train_persona

    log_path = isolated_persona_dirs["data"] / "judge_log.jsonl"
    entries = [_entry("accept", 0.10) for _ in range(5)] + [
        _entry("reject", 0.30) for _ in range(5)
    ]
    _write_judge_log(log_path, entries)
    train_persona(min_samples=10)
    assert load_persona() != DEFAULT_PERSONA

    res = reset_persona()
    assert res["action"] == "reset"
    assert res["removed_file"] is True
    assert load_persona() == DEFAULT_PERSONA

    history = isolated_persona_dirs["cache"] / "persona_history.jsonl"
    assert history.is_file(), "history dosyası reset sonrası korunmalı"
