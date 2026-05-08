# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Patch A — GAP-R5-01 tamper_check path + hash-source tests.

Pilot Round 5 found ``tamper_check._verifier_path`` returned
``verifier.py`` even when the production image had only the Cython
``.so``. Combined with ``ABS_VERIFIER_HASH`` never being set, the
gate was a silent no-op. Patch A resolves the ``.so`` first and
reads the expected hash from ``/etc/abs.verifier.hash`` (file
written by the Dockerfile builder stage).

These tests pin the new resolution behaviour without depending on a
real production image build.
"""

from __future__ import annotations

import hashlib

from app.licensing import tamper_check as tc_mod


def test_verifier_path_prefers_so_over_py(tmp_path, monkeypatch):
    """When both ``verifier*.so`` and ``verifier.py`` exist next to the
    module, the ``.so`` wins — production drops the ``.py`` source so
    the gate must hash the binary it is meant to protect."""

    fake_pkg = tmp_path / "pkg"
    fake_pkg.mkdir()
    (fake_pkg / "verifier.py").write_text("# stripped in prod\n")
    so_path = fake_pkg / "verifier.cpython-311-x86_64-linux-gnu.so"
    so_path.write_bytes(b"\x7fELF...stub")
    fake_module = fake_pkg / "tamper_check.py"
    fake_module.write_text("")
    monkeypatch.setattr(tc_mod, "__file__", str(fake_module))

    resolved = tc_mod._verifier_path()

    assert resolved == so_path


def test_expected_hash_prefers_etc_file_over_env(tmp_path, monkeypatch):
    """``/etc/abs.verifier.hash`` (image-baked) overrides the legacy
    ``ABS_VERIFIER_HASH`` env var. Backwards compatibility falls back
    to the env when the file is absent."""

    hash_file = tmp_path / "abs.verifier.hash"
    hash_file.write_text("aa" * 32 + "\n")
    monkeypatch.setattr(tc_mod, "_HASH_FILE", hash_file)
    monkeypatch.setenv("ABS_VERIFIER_HASH", "bb" * 32)

    assert tc_mod._expected_hash() == "aa" * 32

    hash_file.unlink()
    assert tc_mod._expected_hash() == "bb" * 32


def test_verify_self_integrity_detects_so_tamper(tmp_path, monkeypatch):
    """A byte appended to the ``.so`` flips its sha256; the gate must
    return False so ``assert_self_integrity`` panics on boot."""

    fake_pkg = tmp_path / "pkg"
    fake_pkg.mkdir()
    so_path = fake_pkg / "verifier.cpython-311-x86_64-linux-gnu.so"
    pristine = b"\x7fELF...pristine"
    so_path.write_bytes(pristine)
    fake_module = fake_pkg / "tamper_check.py"
    fake_module.write_text("")
    monkeypatch.setattr(tc_mod, "__file__", str(fake_module))

    expected = hashlib.sha256(pristine).hexdigest()
    hash_file = tmp_path / "abs.verifier.hash"
    hash_file.write_text(expected + "\n")
    monkeypatch.setattr(tc_mod, "_HASH_FILE", hash_file)
    monkeypatch.delenv("ABS_VERIFIER_HASH", raising=False)

    assert tc_mod.verify_self_integrity() is True

    so_path.write_bytes(pristine + b"TAMPER")
    assert tc_mod.verify_self_integrity() is False
