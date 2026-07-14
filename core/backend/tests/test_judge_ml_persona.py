"""ML persona training (logistic regression) testleri."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_judge_dirs(monkeypatch, tmp_path: Path):
    from app.config import settings

    data = tmp_path / "data"
    cache = tmp_path / "cache"
    data.mkdir()
    cache.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "cache_dir", str(cache))
    return {"data": data, "cache": cache}


def _write_log(data_dir: Path, entries: list[dict]) -> None:
    p = data_dir / "judge_log.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _entry(ast: float, llm: float, drift: float, outcome: str) -> dict:
    return {
        "ts": time.time(),
        "source": "test",
        "ast_score": ast,
        "llm_score": llm,
        "persona_drift": drift,
        "outcome": outcome,
    }


def test_train_insufficient_data(isolated_judge_dirs):
    from app.judge.ml_persona import train_ml

    res = train_ml(min_samples=20)
    assert res["action"] == "insufficient_data"
    assert res["samples"] == 0


def test_train_with_sufficient_samples(isolated_judge_dirs):
    from app.judge.ml_persona import model_status, train_ml

    entries = [_entry(8.0, 8.0, 0.1, "accept") for _ in range(15)] + [
        _entry(4.0, 4.0, 0.5, "reject") for _ in range(15)
    ]
    _write_log(isolated_judge_dirs["data"], entries)

    res = train_ml(min_samples=20)
    assert res["action"] == "trained"
    assert res["n_samples"] == 30
    assert len(res["weights"]) == 3
    s = model_status()
    assert s["trained"] is True
    assert s["n_samples"] == 30


def test_predict_high_score_accepts(isolated_judge_dirs):
    from app.judge.ml_persona import predict_accept, train_ml

    entries = [_entry(8.5, 8.5, 0.1, "accept") for _ in range(20)] + [
        _entry(2.0, 2.0, 1.0, "reject") for _ in range(20)
    ]
    _write_log(isolated_judge_dirs["data"], entries)
    train_ml(min_samples=20)

    pred = predict_accept(8.5, 8.0, 0.1)
    assert pred["decision"] == "accept"
    assert pred["p_accept"] > 0.5


def test_predict_low_score_rejects(isolated_judge_dirs):
    from app.judge.ml_persona import predict_accept, train_ml

    entries = [_entry(8.5, 8.5, 0.1, "accept") for _ in range(20)] + [
        _entry(2.0, 2.0, 1.0, "reject") for _ in range(20)
    ]
    _write_log(isolated_judge_dirs["data"], entries)
    train_ml(min_samples=20)

    pred = predict_accept(2.0, 2.0, 1.0)
    assert pred["decision"] == "reject"
    assert pred["p_accept"] < 0.5


def test_predict_without_training_returns_error(isolated_judge_dirs):
    from app.judge.ml_persona import predict_accept

    pred = predict_accept(5.0, 5.0, 0.5)
    assert "error" in pred
