"""G4 — sanity tests for `scripts/seed_demo_tenant.py` + `purge_demo_tenant.py`."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def seed_module(monkeypatch, tmp_path):
    mod = _load("seed_demo_tenant", "seed_demo_tenant.py")
    fixture_path = tmp_path / "fixtures" / "demo_acme_tenant.json"
    audit_dir = tmp_path / ".audit"
    monkeypatch.setattr(mod, "FIXTURE_PATH", fixture_path)
    monkeypatch.setattr(mod, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(mod, "AUDIT_LOG", audit_dir / "demo-acme-seed.log")
    return mod, fixture_path, audit_dir


@pytest.fixture
def purge_module(monkeypatch, tmp_path):
    mod = _load("purge_demo_tenant", "purge_demo_tenant.py")
    fixture_path = tmp_path / "fixtures" / "demo_acme_tenant.json"
    audit_dir = tmp_path / ".audit"
    monkeypatch.setattr(mod, "FIXTURE_PATH", fixture_path)
    monkeypatch.setattr(mod, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(mod, "PURGE_LOG", audit_dir / "demo-acme-purge.log")
    monkeypatch.setattr(mod, "KEY_LOG", audit_dir / "demo-acme-key-rotation.log")
    return mod, fixture_path, audit_dir


def test_seed_writes_fixture_and_idempotent(seed_module):
    mod, fixture_path, _audit = seed_module
    fp1, written1 = mod.write_seed()
    assert written1 is True
    assert fixture_path.exists()
    fp2, written2 = mod.write_seed()
    assert written2 is False
    assert fp1 == fp2


def test_seed_force_rewrites(seed_module):
    mod, fixture_path, _audit = seed_module
    mod.write_seed()
    fp_a = fixture_path.read_text()
    fp, written = mod.write_seed(force=True)
    assert written is True
    assert fixture_path.read_text() == fp_a  # content identical, just re-emitted
    assert isinstance(fp, str) and len(fp) == 64


def test_seed_audit_log_appended(seed_module):
    mod, _fixture, audit_dir = seed_module
    fp, written = mod.write_seed()
    mod.append_audit("seed", fp, written)
    log = audit_dir / "demo-acme-seed.log"
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["tenant_id"] == "demo-acme"
    assert payload["fingerprint"] == fp
    assert payload["action"] == "seed"


def test_purge_removes_fixture_and_rotates_keys(monkeypatch, seed_module, purge_module):
    seed_mod, fixture_path, _ = seed_module
    purge_mod, purge_fixture_path, _audit = purge_module
    monkeypatch.setattr(purge_mod, "FIXTURE_PATH", fixture_path)
    monkeypatch.setattr(seed_mod, "FIXTURE_PATH", fixture_path)
    seed_mod.write_seed()
    assert fixture_path.exists()
    rc = purge_mod.main([])
    assert rc == 0
    assert not fixture_path.exists()
    purge_log = purge_mod.PURGE_LOG.read_text().strip().splitlines()
    key_log = purge_mod.KEY_LOG.read_text().strip().splitlines()
    assert len(purge_log) == 1 and json.loads(purge_log[0])["tenant_id"] == "demo-acme"
    rotated = json.loads(key_log[0])["rotated_keys"]
    assert set(rotated) == set(purge_mod.ROTATED_KEYS)


def test_purge_dry_run_keeps_fixture(seed_module, purge_module):
    seed_mod, fixture_path, _ = seed_module
    purge_mod, _purge_fixture, _audit = purge_module
    purge_mod.FIXTURE_PATH = fixture_path  # type: ignore[attr-defined]
    seed_mod.FIXTURE_PATH = fixture_path  # type: ignore[attr-defined]
    seed_mod.write_seed()
    rc = purge_mod.main(["--dry-run"])
    assert rc == 0
    assert fixture_path.exists()
    assert not purge_mod.PURGE_LOG.exists()
