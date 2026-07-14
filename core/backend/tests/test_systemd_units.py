"""purge systemd unit files (syntax + paths)."""

from __future__ import annotations

import configparser
from pathlib import Path

UNITS_DIR = Path(__file__).resolve().parents[3] / "infra" / "systemd"


def _parse(path: Path) -> configparser.RawConfigParser:
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(path, encoding="utf-8")
    return cfg


def test_purge_service_unit_present_and_parseable():
    svc = UNITS_DIR / "abs-purge-deleted-accounts.service"
    assert svc.exists(), f"missing service unit at {svc}"
    cfg = _parse(svc)
    assert cfg.has_section("Service")
    assert cfg.get("Service", "Type") == "oneshot"
    exec_start = cfg.get("Service", "ExecStart")
    assert "purge_deleted_accounts.py" in exec_start
    assert exec_start.startswith("/usr/bin/python3")


def test_purge_timer_unit_runs_daily_at_03_00():
    tmr = UNITS_DIR / "abs-purge-deleted-accounts.timer"
    assert tmr.exists(), f"missing timer unit at {tmr}"
    cfg = _parse(tmr)
    assert cfg.has_section("Timer")
    assert cfg.get("Timer", "OnCalendar") == "*-*-* 03:00:00"
    assert cfg.getboolean("Timer", "Persistent") is True
    assert cfg.get("Timer", "Unit") == "abs-purge-deleted-accounts.service"


def test_purge_timer_install_section_targets_timers():
    tmr = UNITS_DIR / "abs-purge-deleted-accounts.timer"
    cfg = _parse(tmr)
    assert cfg.has_section("Install")
    assert cfg.get("Install", "WantedBy") == "timers.target"
