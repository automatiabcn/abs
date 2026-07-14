"""Win-rate eval harness contract.

This test pins the harness's pure-function behaviour so future edits
don't silently break the artifact format. It does NOT call any live
provider — that part is exercised by `scripts/eval/multimodel_winrate.py`
via `--limit 3` smoke runs gated on `GROQ_API_KEY` /
`ANTHROPIC_API_KEY`.

What we lock down:
  1. The dataset fixture exists, parses, and ships 30 rows balanced
     across the three task categories (10 each).
  2. `aggregate()` reports `unmeasured` (None) when no head-to-head
     pairs landed, and computes the win_rate formula
     (gpt_oss_wins + 0.5 * tie) / contested otherwise.
  3. Offline mode produces a markdown artifact + JSON sidecar in
     `artifacts/promise_verify/` so CI / founder audits can reference
     a stable path.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest


REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/eval/multimodel_winrate.py"
DATASET = REPO / "core/backend/tests/fixtures/golden_eval_multimodel.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("multimodel_winrate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_promise_v4_dataset_balanced_after_v2_expansion():
    """The dataset grew from 30 → 100 rows with the consensus eval.

    Locking the new size + per-category split so a future drop in
    coverage trips CI rather than silently weakening the win-rate
    statistical power.
    """
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(rows) == 100, f"expected 100 rows, got {len(rows)}"
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    assert counts == {"code": 25, "analysis": 25, "translation": 25, "writing": 25}, (
        counts
    )
    for r in rows:
        assert {"id", "category", "task", "expected_traits"} <= set(r.keys())
        assert r["task"].strip(), f"empty task in {r['id']}"
        assert isinstance(r["expected_traits"], list)
        assert len(r["expected_traits"]) >= 3


def test_promise_v4_aggregate_unmeasured_when_no_contest():
    mod = _load_module()
    results = [
        {"id": "x", "verdict": "claude_unavailable"},
        {"id": "y", "verdict": "skipped"},
    ]
    summary = mod.aggregate(results)
    assert summary["win_rate"] is None
    assert summary["contested"] == 0


def test_promise_v4_aggregate_winrate_math():
    mod = _load_module()
    results = [
        {"id": "1", "verdict": "gpt_oss_wins"},
        {"id": "2", "verdict": "gpt_oss_wins"},
        {"id": "3", "verdict": "claude_wins"},
        {"id": "4", "verdict": "tie"},
    ]
    summary = mod.aggregate(results)
    assert summary["contested"] == 4
    # (2 + 0.5 * 1) / 4 == 0.625
    assert summary["win_rate"] == pytest.approx(0.625, abs=1e-9)


def test_promise_v4_offline_run_produces_artifacts(tmp_path, monkeypatch):
    """The harness must always leave a markdown + JSON artifact behind
    so the audit trail is reproducible. Offline mode is the cheap CI
    smoke that proves the writer path."""
    mod = _load_module()
    art = tmp_path / "sprint_13_winrate.md"
    js = tmp_path / "sprint_13_winrate.json"
    monkeypatch.setattr(mod, "ARTIFACT", art)
    monkeypatch.setattr(mod, "RESULTS_JSON", js)
    rc = subprocess.call(
        [sys.executable, str(SCRIPT), "--offline", "--limit", "3"],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
    )
    # Subprocess writes to the real ARTIFACT path; verify those exist
    # rather than the monkeypatched tmp files (subprocess starts fresh).
    real_art = REPO / "artifacts/promise_verify/sprint_13_winrate.md"
    real_js = REPO / "artifacts/promise_verify/sprint_13_winrate.json"
    assert rc == 0
    assert real_art.exists()
    assert real_js.exists()
    body = json.loads(real_js.read_text(encoding="utf-8"))
    assert body["mode"] in {"offline", "live", "live-no-claude"}
    assert "summary" in body and "counts" in body["summary"]
