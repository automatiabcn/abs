"""Dockerfile + docker-compose + init_vault.sh content checks."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_dockerfile_contains_sops_age_install():
    dockerfile = (REPO_ROOT / "core" / "backend" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "/usr/local/bin/sops" in dockerfile
    assert "age-keygen" in dockerfile
    assert "SOPS_VERSION" in dockerfile
    assert "AGE_VERSION" in dockerfile
    # Builder stage'de install + runtime stage'e copy
    assert "FROM base AS builder" in dockerfile
    assert "FROM base AS runtime" in dockerfile
    assert "/app/vault-key" in dockerfile  # mkdir runtime


def test_compose_has_vault_key_volume():
    compose = (REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "abs-vault-key" in compose
    assert "/app/vault-key:ro" in compose  # read-only mount


def test_init_vault_sh_executable_and_uses_age_keygen():
    script = REPO_ROOT / "infra" / "scripts" / "init_vault.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "age-keygen" in text
    assert "abs-vault-key" in text
    # idempotent guard
    assert "if [ -f /vault-key/age.key ]" in text or "atlandi" in text.lower()
