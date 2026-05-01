"""feature_nudge — 15 Bash + 8 MCP nudge + rate-limit."""

from __future__ import annotations

import pytest

from app.config import settings
from app.hooks import feature_nudge


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))


def test_code_write_triggers_qual_code_nudge():
    msg = feature_nudge.maybe_feature_nudge_bash(
        'ask "python function yaz" gptoss'
    )
    assert "qual-code" in msg


def test_compare_triggers_race_nudge():
    msg = feature_nudge.maybe_feature_nudge_bash(
        'ask "compare React vs Vue" kimi'
    )
    assert "race" in msg


def test_rag_keyword_triggers_rag_nudge():
    msg = feature_nudge.maybe_feature_nudge_bash(
        'ask "projemde similar pattern var mi" gptoss'
    )
    assert "RAG" in msg


def test_docs_keyword_triggers_docs_nudge():
    msg = feature_nudge.maybe_feature_nudge_bash(
        'ask "readme yaz proje icin" qwen32b'
    )
    assert "docs" in msg or "Dokümantasyon" in msg or "fs-doc" in msg


def test_rate_limit_prevents_duplicate_within_window():
    a = feature_nudge.maybe_feature_nudge_bash('ask "python function yaz" gptoss')
    b = feature_nudge.maybe_feature_nudge_bash('ask "python function yaz" gptoss')
    assert a != ""
    assert b == ""  # 10dk içinde 2. nudge susturulur


def test_mcp_idle_nudge_for_ask_gptoss():
    msg = feature_nudge.maybe_feature_nudge_mcp("ask_gptoss", {"prompt": "x"})
    assert "qual_code" in msg or "race" in msg
