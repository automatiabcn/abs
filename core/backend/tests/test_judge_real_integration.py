"""022 Modul G — Judge feed real integration (placeholder kalktı)."""

from __future__ import annotations


def test_build_judge_returns_real_signal_when_aggregate_works(monkeypatch):
    """Judge feed `judge.stats.aggregate()` veriyorsa real:True döner."""
    fake_stats = {
        "total_count": 12,
        "avg_score": 7.4,
        "accept_rate": 0.83,
    }

    import app.api.stream as stream_mod
    import app.judge.stats as stats_mod

    monkeypatch.setattr(stats_mod, "aggregate", lambda *a, **k: fake_stats)
    # Cache temizle ki yeni mock görsün
    stream_mod._JUDGE_CACHE["data"] = None
    stream_mod._JUDGE_CACHE["ts"] = 0

    out = stream_mod._build_judge_placeholder()
    assert out["real"] is True
    assert out["score"] == 7.4
    assert "12 patch" in out["summary"]
