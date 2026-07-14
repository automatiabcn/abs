"""Judge log + stats — 5 test (rotation, outcome, drift_signal)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.config import settings
from app.judge import log as jl
from app.judge import stats as js


@pytest.fixture(autouse=True)
def _tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


def test_log_judgment_writes_jsonl_and_returns_id():
    result = {
        "combined_score": 7.5,
        "ast_score": 7.0,
        "llm_score": 8.0,
        "fingerprint_details": [
            {"metric": "docstring_ratio", "actual": 0.7, "target": 0.6},
        ],
    }
    jid = jl.log_judgment(result, file_path="x.py")
    assert len(jid) == 12
    p = Path(settings.data_dir) / "judge_log.jsonl"
    assert p.is_file()
    line = p.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(line)
    assert parsed["id"] == jid
    assert parsed["combined_score"] == 7.5
    assert parsed["outcome"] is None


def test_update_outcome_marks_accept():
    jid = jl.log_judgment({"combined_score": 6.0}, file_path="y.py")
    assert jl.update_outcome(jid, "accept") is True
    entries = jl.read_recent(limit=10)
    assert any(e["id"] == jid and e["outcome"] == "accept" for e in entries)


def test_update_outcome_invalid_value_returns_false():
    jid = jl.log_judgment({"combined_score": 5.0})
    assert jl.update_outcome(jid, "yes") is False


def test_aggregate_window_7_days_basic():
    for s in (7.0, 8.0, 9.0):
        jl.log_judgment({"combined_score": s, "ast_score": s, "llm_score": s})
    agg = js.aggregate(window_days=7)
    assert agg["count"] == 3
    assert agg["avg_combined"] == 8.0
    assert agg["drift_signal"] == "stable"  # önceki window boş


def test_drift_signal_tightening_detects_drop(monkeypatch):
    """Previous window 7.5 average, current 6.5 → tightening (score dropped)."""
    p = Path(settings.data_dir) / "judge_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    lines = []
    for s in (7.5, 7.5, 7.5):
        lines.append(
            json.dumps(
                {
                    "id": "p" + str(s),
                    "ts": now - 10 * 86400,  # önceki window
                    "combined_score": s,
                    "outcome": None,
                }
            )
        )
    for s in (6.5, 6.5, 6.5):
        lines.append(
            json.dumps(
                {
                    "id": "c" + str(s),
                    "ts": now - 1 * 86400,
                    "combined_score": s,
                    "outcome": None,
                }
            )
        )
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    agg = js.aggregate(window_days=7)
    assert agg["drift_signal"] == "tightening"
