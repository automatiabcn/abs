# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (f) — 3rd-eye audit.

Regression: the panel judge feed (_build_judge_placeholder) read keys
avg_score/avg + accept_rate/accepted_pct, but judge.stats.aggregate() emits
avg_combined / count / outcome_counts. So the feed showed score=None and 0%
accept-rate on every render — even though it was flagged 'real':True — whenever
there were real judgments. Now it reads the keys aggregate actually returns.
"""

from __future__ import annotations

from app.api import stream as stream_mod


def test_judge_feed_uses_real_aggregate_keys(monkeypatch):
    # bypass the 60s feed cache
    stream_mod._JUDGE_CACHE["data"] = None
    stream_mod._JUDGE_CACHE["ts"] = 0.0

    def _fake_aggregate(*args, **kwargs):
        return {"count": 4, "avg_combined": 8.5,
                "outcome_counts": {"accept": 3, "reject": 1}}

    monkeypatch.setattr("app.judge.stats.aggregate", _fake_aggregate)

    out = stream_mod._build_judge_placeholder()
    assert out["score"] == 8.5                     # was None (wrong key)
    assert "Son 4 patch" in out["summary"]
    assert "%75" in out["summary"]                 # 3/4 accepted — was %0
