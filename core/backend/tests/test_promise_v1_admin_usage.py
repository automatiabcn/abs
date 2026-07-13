"""BUG-V1 — `/v1/admin/usage` contract test.

The PROMISE.md vow:
  - real-time `Free path: X %` + `Claude budget: Y %` widget on /admin/usage.

This test pins the JSON shape that the Tremor metric tiles + 7-day
chart subscribe to, plus the auth gate (401 without bearer) and the
cold-install graceful fallback.
"""

from __future__ import annotations


import bcrypt
import pytest

from app.api.admin import usage as usage_module
from app.config import settings
from app.observability import quota_monitor


def _set_password(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )


def _login(client, monkeypatch) -> str:
    _set_password(monkeypatch, "s3cret")
    return client.post("/v1/admin/login", json={"password": "s3cret"}).json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin(monkeypatch):
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


@pytest.fixture
def _empty_usage_log(tmp_path, monkeypatch):
    """Point the usage log + quota ledger at empty tmp paths so the
    test runs deterministically against a cold install."""
    empty = tmp_path / "rag_usage.jsonl"
    monkeypatch.setattr(settings, "usage_log_path", str(empty), raising=False)
    monkeypatch.setattr(
        usage_module,
        "_usage_log_path",
        lambda: empty,
    )
    quota_log = tmp_path / "claude_tokens.jsonl"
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_LEDGER", str(quota_log))
    monkeypatch.setattr(
        quota_monitor,
        "_ledger_path",
        lambda: quota_log,
    )
    # /v1/admin/usage now merges the live DB usage_log table (cascade write
    # path) on top of the JSONL ledger, so a deterministic "cold install"
    # also needs the DB table empty.
    from app.services import usage_log as _usage_log

    _usage_log.reset_for_tests()
    return empty, quota_log


def test_promise_v1_unauthenticated_returns_401(client):
    r = client.get("/v1/admin/usage")
    assert r.status_code == 401


def test_promise_v1_cold_install_zero_payload(client, monkeypatch, _empty_usage_log):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    # Top-level shape (the Tremor tiles bind to these keys).
    assert {
        "month",
        "claude",
        "free_path",
        "paid_path",
        "total_calls_24h",
        "provider_mix_24h",
        "daily_trend",
    } <= set(body.keys())
    # Claude block carries quota state (PROMISE.md "Claude budget: Y %").
    claude = body["claude"]
    assert {
        "limit_tokens",
        "used_tokens",
        "used_pct",
        "over_warn",
        "over_block",
        "banner",
    } <= set(claude.keys())
    assert claude["used_tokens"] == 0
    assert claude["used_pct"] == 0.0
    assert claude["over_warn"] is False
    assert claude["over_block"] is False
    # Free path tile (PROMISE.md "Free path: X %"). With zero calls there is no
    # ratio — pct_24h is None (tile shows "—"), not a fabricated 100 %.
    assert body["free_path"]["calls_24h"] == 0
    assert body["free_path"]["pct_24h"] is None
    # 7-day trend always returns 7 dense buckets so the chart never empties.
    assert isinstance(body["daily_trend"], list)
    assert len(body["daily_trend"]) == 7
    for bucket in body["daily_trend"]:
        assert {"day", "claude_tokens"} <= set(bucket.keys())
        assert bucket["claude_tokens"] == 0


def test_promise_v1_aggregates_recent_usage(
    client, monkeypatch, _empty_usage_log, tmp_path
):
    """A handful of free + paid usage rows aggregate into the right
    24h tile counts."""
    import datetime as dt
    import json

    empty, _ = _empty_usage_log
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = [
        {
            "timestamp": now,
            "model_version": "groq/gpt-oss-120b",
            "input_tokens": 5,
            "output_tokens": 10,
        },
        {
            "timestamp": now,
            "model_version": "groq/llama-3.3-70b",
            "input_tokens": 5,
            "output_tokens": 10,
        },
        {
            "timestamp": now,
            "model_version": "claude-sonnet-4-5",
            "input_tokens": 100,
            "output_tokens": 200,
        },
    ]
    with empty.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/usage",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["total_calls_24h"] == 3
    assert body["free_path"]["calls_24h"] == 2
    assert body["paid_path"]["calls_24h"] == 1
    # 2/3 -> 0.6667 (rounded to 4 decimals)
    assert body["free_path"]["pct_24h"] == pytest.approx(0.6667, abs=1e-3)
    assert body["provider_mix_24h"].get("groq") == 2
    assert body["provider_mix_24h"].get("anthropic") == 1
