# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""rag_index path-traversal guard (CWE-22) — secret/system paths must be
refused, legitimate document paths allowed."""

from __future__ import annotations

from pathlib import Path

from app.rag.indexer import _unsafe_index_path


def test_blocks_vault_key():
    assert _unsafe_index_path(Path("/app/vault-key/age.key")) is not None


def test_blocks_system_dirs():
    assert _unsafe_index_path(Path("/etc/passwd")) is not None
    assert _unsafe_index_path(Path("/etc/hostname")) is not None
    assert _unsafe_index_path(Path("/proc/self/environ")) is not None
    assert _unsafe_index_path(Path("/root/.bashrc")) is not None


def test_blocks_secret_suffixes_and_names():
    assert _unsafe_index_path(Path("/app/data/abs.db")) is not None
    assert _unsafe_index_path(Path("/app/data/secrets.yaml")) is not None
    assert _unsafe_index_path(Path("/somewhere/key.pem")) is not None
    assert _unsafe_index_path(Path("/somewhere/.env")) is not None
    assert _unsafe_index_path(Path("/app/data/admin_credentials.json")) is not None


def test_allows_legit_docs():
    assert _unsafe_index_path(Path("/app/data/rag-docs/readme.md")) is None
    assert _unsafe_index_path(Path("/app/data/docs/guide.txt")) is None
    assert _unsafe_index_path(Path("/mnt/customer-docs/notes.md")) is None
