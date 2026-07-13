"""027 Modul A — sops binary detection + production fail-fast."""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.config import settings
from app.vault import runner


def test_sops_version_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert runner.sops_version() is None


def test_sops_version_parses_first_line(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/sops")

    def _run(*args, **kwargs):
        return SimpleNamespace(stdout="sops 3.7.3 (latest)\n...\n", returncode=0)

    monkeypatch.setattr(subprocess, "run", _run)
    assert runner.sops_version() == "3.7.3"


def test_check_production_vault_dev_mode_warns_only(monkeypatch, caplog):
    monkeypatch.setattr(settings, "vault_require_sops", False)
    monkeypatch.setattr(runner, "sops_available", lambda: False)
    # Should not raise
    runner.check_production_vault()
    assert any("dev fallback" in (r.getMessage() or "") for r in caplog.records)


def test_check_production_vault_prod_mode_fails_when_missing(monkeypatch):
    monkeypatch.setattr(settings, "vault_require_sops", True)
    monkeypatch.setattr(runner, "sops_available", lambda: False)
    with pytest.raises(RuntimeError, match="sops/age binary not found"):
        runner.check_production_vault()


def test_check_production_vault_prod_mode_rejects_old_version(monkeypatch):
    monkeypatch.setattr(settings, "vault_require_sops", True)
    monkeypatch.setattr(settings, "vault_min_sops_version", "3.7.0")
    monkeypatch.setattr(runner, "sops_available", lambda: True)
    monkeypatch.setattr(runner, "sops_version", lambda: "3.5.0")
    with pytest.raises(RuntimeError, match=r"3\.5\.0 < required 3\.7\.0"):
        runner.check_production_vault()
