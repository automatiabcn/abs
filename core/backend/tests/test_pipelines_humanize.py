"""Humanize scorer testleri."""

from __future__ import annotations

from app.pipelines.humanize.scorer import humanize_score_text


def test_humanize_score_empty_text_is_zero():
    s = humanize_score_text("")
    assert s.score == 0.0
    assert s.matches == []


def test_humanize_score_detects_ai_stock_phrase():
    s = humanize_score_text("As an AI, I cannot provide real-time data. In conclusion, it is important to note...")
    assert s.score > 0
    assert any("as an ai" in m for m in s.matches)


def test_humanize_score_clean_turkish_text_is_low():
    s = humanize_score_text("Bugün pazar. Dışarı çıktım. Kahve içtim. Keyifliydi.")
    assert s.score <= 0.2
