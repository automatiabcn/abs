"""enrichment — 6-katman quality gate."""

from __future__ import annotations

import pytest

from app.config import settings
from app.hooks import enrichment


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))


def test_big_turkish_md_triggers_gate():
    content = "# Kılavuz\n\n" + ("Bu Türkçe açıklama uzun bir paragraftır. " * 200)
    msg = enrichment.maybe_enrichment_notice(
        "Write", {"file_path": "/x/GUIDE.md", "content": content}
    )
    assert "ENRICHMENT GATE" in msg
    assert "qual_tr" in msg or "qual_analysis" in msg


def test_small_md_below_min_size_ignored():
    msg = enrichment.maybe_enrichment_notice(
        "Write", {"file_path": "/x/tiny.md", "content": "kısa metin"}
    )
    assert msg == ""


def test_unsupported_extension_ignored():
    msg = enrichment.maybe_enrichment_notice(
        "Write", {"file_path": "/x/binary.xyz", "content": "x" * 5000}
    )
    assert msg == ""


def test_non_write_tool_ignored():
    msg = enrichment.maybe_enrichment_notice(
        "Bash", {"command": "echo hello"}
    )
    assert msg == ""
