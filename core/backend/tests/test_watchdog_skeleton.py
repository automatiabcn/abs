"""014 — Watchdog skeleton testleri (infra/watchdog import path).

Watchdog backend container'inda calismaz; test sys.path manipulasyonu ile
infra/ paketini import eder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "infra"))


def test_scan_all_returns_list():
    from watchdog.scanner import list_feeds, scan_all

    feeds = list_feeds()
    assert len(feeds) >= 4
    out = scan_all()
    assert isinstance(out, list)
    assert len(out) == len(feeds)
    for entry in out:
        assert "provider" in entry
        assert "scanned_at" in entry
        assert entry["status"] == "stub"


@pytest.mark.asyncio
async def test_alerter_no_webhook_returns_false(monkeypatch):
    from watchdog.alerter import send_discord_alert

    monkeypatch.delenv("WATCHDOG_DISCORD_WEBHOOK", raising=False)
    result = await send_discord_alert("test message")
    assert result is False


def test_watchdog_readme_documents_deploy():
    readme = REPO_ROOT / "infra" / "watchdog" / "README.md"
    text = readme.read_text(encoding="utf-8")
    # What the README owes a reader is how to deploy it: a VPS, the alert
    # webhook, the cron entry. Which hosting company we happen to use is our
    # business, not the reader's.
    assert "VPS" in text
    assert "WATCHDOG_DISCORD_WEBHOOK" in text
    assert "watchdog.cron" in text
