"""Defensive validation regression (repo audit round).

Negative token/cost values must never reach — or shrink — the metering
aggregates that quota gating reads. A single negative row could otherwise
widen a customer's effective quota.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services import usage_log
from app.observability import quota_monitor


def test_usage_log_drops_negative_cost(monkeypatch):
    appended = {}

    class _DB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def add(self, row):
            appended["row"] = row

        def commit(self):
            appended["committed"] = True

    monkeypatch.setattr(usage_log, "Session", lambda engine: _DB())
    monkeypatch.setattr(usage_log, "get_engine", lambda: object())

    # negative cost is rejected before any DB write
    usage_log.append("groq", 100, cost_usd=-5.0)
    assert "row" not in appended

    # positive values still write
    usage_log.append("groq", 100, cost_usd=0.5)
    assert "row" in appended


def test_quota_read_used_ignores_negative_and_garbage_rows(tmp_path):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger = tmp_path / "quota_ledger.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"month": month, "tokens": 1000},
                {"month": month, "tokens": -999999},   # poison row
                {"month": month, "tokens": "abc"},      # garbage
                {"month": month, "tokens": 500},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    used = quota_monitor._read_used(ledger=ledger, month=month)
    assert used == 1500  # only the two positive rows count
