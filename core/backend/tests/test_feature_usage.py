"""Feature usage tracker + idle detection."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.observability import feature_usage as fu


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "feature.jsonl"
    monkeypatch.setenv("ABS_FEATURE_USAGE_LEDGER", str(path))
    return path


def test_record_appends_row(ledger):
    fu.record(
        "abs.qual_code", kind="tool", tenant_id="acme", duration_ms=120, ledger=ledger
    )
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["feature"] == "abs.qual_code"
    assert rows[0]["tenant_id"] == "acme"
    assert rows[0]["duration_ms"] == 120


def test_report_zero_state_marks_everything_idle(ledger):
    rep = fu.report(ledger=ledger)
    assert rep.total_calls == 0
    assert all(s.idle for s in rep.stats)
    assert rep.idle_pct == 1.0
    assert rep.over_idle_threshold is True


def test_report_counts_within_window(ledger):
    for _ in range(10):
        fu.record("abs.qual_code", ledger=ledger)
    for _ in range(5):
        fu.record("abs.rag_query", ledger=ledger)
    rep = fu.report(ledger=ledger)
    by_feature = {s.feature: s for s in rep.stats}
    assert by_feature["abs.qual_code"].calls == 10
    assert by_feature["abs.rag_query"].calls == 5
    assert rep.total_calls == 15


def test_report_excludes_rows_outside_window(ledger):
    # Inject a stale row with timestamp 90 days ago.
    stale_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat(
        timespec="seconds"
    )
    ledger.write_text(
        json.dumps({"ts": stale_ts, "feature": "abs.qual_code", "kind": "tool"}) + "\n"
    )
    fu.record("abs.qual_code", ledger=ledger)
    rep = fu.report(window_days=30, ledger=ledger)
    by_feature = {s.feature: s for s in rep.stats}
    assert by_feature["abs.qual_code"].calls == 1


def test_idle_threshold_drops_below_20pct_when_features_used(ledger):
    """Use most of the catalog and confirm idle_pct stays under 20%."""
    used = fu.KNOWN_FEATURES[: int(len(fu.KNOWN_FEATURES) * 0.85)]
    for f in used:
        fu.record(f, ledger=ledger)
    rep = fu.report(ledger=ledger)
    assert rep.idle_pct <= 0.20
    assert rep.over_idle_threshold is False


def test_kind_classification():
    assert fu._kind_for("abs.qual_code") == "tool"
    assert fu._kind_for("cascade.race_code") == "cascade"
    assert fu._kind_for("judge.senior") == "pipeline"
    assert fu._kind_for("workflow.synthesize") == "workflow"
    assert fu._kind_for("zzz.unknown") == "uncategorised"


@pytest.mark.parametrize(
    "kw,expect_substr",
    [
        (["code", "function"], "abs.qual_code"),
        (["analyze", "compare"], "abs.qual_analysis"),
        (["translate", "spanish"], "abs.qual_translate"),
    ],
)
def test_suggest_alternative_hits_pipelines(kw, expect_substr):
    s = fu.suggest_alternative(kw)
    assert s is not None
    assert expect_substr in s


def test_suggest_alternative_no_match():
    assert fu.suggest_alternative(["unrelated", "topic"]) is None


def test_known_features_count_at_least_22():
    """Catalog must cover the ABS-specific node types the workflow builder advertises."""
    assert len(fu.KNOWN_FEATURES) >= 22


def test_record_100_calls_idle_drops(ledger):
    """Mock 100 calls across 5 features, verify last_seen + counts."""
    sample = [
        "abs.qual_code",
        "abs.qual_analysis",
        "abs.rag_query",
        "abs.cerbos_check",
        "judge.senior",
    ]
    for i in range(100):
        fu.record(sample[i % len(sample)], ledger=ledger)
    rep = fu.report(ledger=ledger)
    used = {s.feature for s in rep.stats if not s.idle}
    assert set(sample).issubset(used)
    assert rep.total_calls == 100
    # Each used feature had 20 calls
    by_feature = {s.feature: s for s in rep.stats}
    for f in sample:
        assert by_feature[f].calls == 20
        assert by_feature[f].last_used is not None


def test_reset_for_tests(ledger):
    fu.record("abs.qual_code", ledger=ledger)
    fu.reset_for_tests(ledger=ledger)
    assert fu.report(ledger=ledger).total_calls == 0
