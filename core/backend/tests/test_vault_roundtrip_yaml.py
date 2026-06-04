# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Regression: encrypt_all/decrypt_all must force sops --input-type yaml.

The temp file ends in '.yaml.tmp'; sops infers '.tmp' as binary and wraps the
whole document under a single `data:` key, breaking the flat round-trip
(read_secret -> None, every deploy silently fell back to plaintext .env). The
suite previously mocked sops, so this slipped through — assert the type flags
are present so it cannot regress."""

from __future__ import annotations


def test_encrypt_all_passes_yaml_type(monkeypatch, tmp_path):
    from app.config import settings
    from app.vault import runner

    monkeypatch.setattr(settings, "vault_secrets_path", str(tmp_path / "secrets.yaml"))
    monkeypatch.setattr(runner, "sops_available", lambda: True)
    monkeypatch.setattr(runner, "master_key_exists", lambda: True)
    monkeypatch.setattr(runner, "_read_age_recipient", lambda: "age1testrecipient")

    captured: dict = {}

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.encrypt_all({"groq_api_key": "x"})

    cmd = captured["cmd"]
    assert "--input-type" in cmd and "--output-type" in cmd
    # the value after each type flag must be yaml
    assert cmd[cmd.index("--input-type") + 1] == "yaml"
    assert cmd[cmd.index("--output-type") + 1] == "yaml"


def test_decrypt_all_passes_yaml_type(monkeypatch, tmp_path):
    from app.config import settings
    from app.vault import runner

    sp = tmp_path / "secrets.yaml"
    sp.write_text("encrypted-placeholder\n", encoding="utf-8")
    monkeypatch.setattr(settings, "vault_secrets_path", str(sp))
    monkeypatch.setattr(runner, "sops_available", lambda: True)
    monkeypatch.setattr(runner, "master_key_exists", lambda: True)

    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "groq_api_key: x\n"
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    out = runner.decrypt_all()

    assert out == {"groq_api_key": "x"}  # flat, not {"data": ...}
    assert "--input-type" in captured["cmd"]


def test_decrypt_all_unwraps_legacy_data_format(monkeypatch, tmp_path):
    """Pre-fix vaults wrap everything under `data:` (binary mode). decrypt_all
    must transparently unwrap so upgraded installs recover old secrets."""
    from app.config import settings
    from app.vault import runner

    sp = tmp_path / "secrets.yaml"
    sp.write_text("placeholder\n", encoding="utf-8")
    monkeypatch.setattr(settings, "vault_secrets_path", str(sp))
    monkeypatch.setattr(runner, "sops_available", lambda: True)
    monkeypatch.setattr(runner, "master_key_exists", lambda: True)

    class _R:
        returncode = 0
        # the legacy binary-wrapped payload sops emits on decrypt
        stdout = "data: |\n  groq_api_key: gsk_legacy\n  gemini_api_key: AIzaOld\n"
        stderr = ""

    monkeypatch.setattr(runner.subprocess, "run", lambda cmd, **kw: _R())
    out = runner.decrypt_all()
    assert out == {"groq_api_key": "gsk_legacy", "gemini_api_key": "AIzaOld"}
