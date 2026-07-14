"""News watcher source registry tests."""

from __future__ import annotations

import pytest

from app.watcher.sources import (
    NewsItem,
    RateLimitExceeded,
    Source,
    WatcherRegistry,
)


def _make_items(prefix: str, n: int) -> list[NewsItem]:
    return [
        NewsItem(
            source=prefix,
            url=f"https://example.com/{prefix}/{i}",
            title=f"{prefix} item {i}",
            published_at="2026-04-28T00:00:00Z",
            summary=f"summary {i}",
        )
        for i in range(n)
    ]


def test_fetch_one_dedupes_repeated_calls() -> None:
    payload = _make_items("github", 3)

    def fetch():
        return list(payload)

    reg = WatcherRegistry()
    reg.register(Source(name="github", fetch=fetch, rate_per_minute=10))
    first = reg.fetch_one("github")
    second = reg.fetch_one("github")
    assert len(first) == 3
    assert second == []  # all already seen


def test_fetch_unknown_source_raises() -> None:
    reg = WatcherRegistry()
    with pytest.raises(KeyError):
        reg.fetch_one("unknown")


def test_register_duplicate_raises() -> None:
    reg = WatcherRegistry()
    reg.register(Source(name="x", fetch=lambda: []))
    with pytest.raises(ValueError):
        reg.register(Source(name="x", fetch=lambda: []))


def test_rate_limit_exceeded() -> None:
    reg = WatcherRegistry()
    reg.register(
        Source(name="rl", fetch=lambda: _make_items("rl", 1), rate_per_minute=1)
    )
    reg.fetch_one("rl")
    with pytest.raises(RateLimitExceeded):
        reg.fetch_one("rl")


def test_fetch_all_returns_per_source_results() -> None:
    reg = WatcherRegistry()
    reg.register(Source(name="a", fetch=lambda: _make_items("a", 2)))
    reg.register(Source(name="b", fetch=lambda: _make_items("b", 1)))
    out = reg.fetch_all()
    assert set(out.keys()) == {"a", "b"}
    assert sum(len(v) for v in out.values()) == 3


def test_news_item_fingerprint_stable() -> None:
    item = NewsItem(
        source="hn",
        url="https://news.ycombinator.com/item?id=1",
        title="LangFuse",
        published_at="2026-04-28T00:00:00Z",
        summary="release",
    )
    assert item.fingerprint() == item.fingerprint()
    assert len(item.fingerprint()) == 16


def test_list_sources_sorted() -> None:
    reg = WatcherRegistry()
    reg.register(Source(name="reddit", fetch=lambda: []))
    reg.register(Source(name="arxiv", fetch=lambda: []))
    assert reg.list_sources() == ["arxiv", "reddit"]
