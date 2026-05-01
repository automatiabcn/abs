"""T-050 — News digest tests."""

from __future__ import annotations

import pytest

from app.watcher.digest import build_digest, default_summariser
from app.watcher.sources import NewsItem


def _items(n: int) -> list[NewsItem]:
    return [
        NewsItem(
            source="hn",
            url=f"https://news/{i}",
            title=f"item {i}",
            published_at="2026-04-28",
            summary=f"first sentence {i}. second sentence {i}.",
        )
        for i in range(n)
    ]


def test_default_summariser_picks_first_sentence() -> None:
    out = default_summariser(_items(2))
    assert out[0].summary == "first sentence 0"


def test_build_digest_caps_max_items() -> None:
    report = build_digest(items=_items(50), max_items=5)
    assert len(report.items) == 5
    assert report.n_total == 50


def test_build_digest_uses_supplied_summariser() -> None:
    def custom(items):  # noqa: ANN001
        from app.watcher.digest import DigestEntry

        return [
            DigestEntry(
                source=i.source,
                title=i.title.upper(),
                url=i.url,
                summary="LLM summary",
            )
            for i in items
        ]

    report = build_digest(items=_items(2), summariser=custom)
    assert report.items[0].title == "ITEM 0"
    assert all(e.summary == "LLM summary" for e in report.items)


def test_build_digest_to_markdown_contains_titles() -> None:
    md = build_digest(items=_items(2)).to_markdown()
    assert "item 0" in md
    assert "item 1" in md
    assert md.startswith("# ABS Watcher Digest")


def test_build_digest_rejects_zero_max_items() -> None:
    with pytest.raises(ValueError):
        build_digest(items=_items(1), max_items=0)
