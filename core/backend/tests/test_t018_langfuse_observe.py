"""T-018 — LangFuse @observe wrapper + Cerbos lifespan pre-warm tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.observability import langfuse_client as lc


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "langfuse_enabled", False, raising=False)
    monkeypatch.setattr(settings, "langfuse_public_key", "", raising=False)
    monkeypatch.setattr(settings, "langfuse_secret_key", "", raising=False)
    lc.close_langfuse()
    monkeypatch.setattr(lc, "_real_observe", None, raising=False)
    yield
    lc.close_langfuse()


def test_observe_passthrough_when_disabled() -> None:
    @lc.observe(name="rag.query")
    def echo(value: int) -> int:
        return value * 2

    assert echo(3) == 6


def test_observe_bare_decorator_form() -> None:
    @lc.observe
    def double(x):  # noqa: ANN001
        return x + 1

    assert double(4) == 5


def test_is_enabled_requires_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "langfuse_enabled", True, raising=False)
    assert lc.is_enabled() is False
    monkeypatch.setattr(settings, "langfuse_public_key", "pk", raising=False)
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk", raising=False)
    assert lc.is_enabled() is True


def test_get_langfuse_returns_none_when_disabled() -> None:
    assert lc.get_langfuse() is None


def test_get_langfuse_invokes_sdk_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "langfuse_enabled", True, raising=False)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk", raising=False)
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk", raising=False)
    monkeypatch.setattr(settings, "langfuse_host", "http://x", raising=False)

    class _FakeLangfuse:
        instances: list = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            _FakeLangfuse.instances.append(self)

        def flush(self) -> None:
            pass

    fake_module = MagicMock()
    fake_module.Langfuse = _FakeLangfuse
    monkeypatch.setitem(__import__("sys").modules, "langfuse", fake_module)

    cli = lc.get_langfuse()
    assert cli is not None
    assert _FakeLangfuse.instances[0].kwargs["public_key"] == "pk"


def test_observe_uses_real_decorator_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "langfuse_enabled", True, raising=False)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk", raising=False)
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk", raising=False)

    captured: dict = {}

    def fake_observe(**kwargs):  # noqa: ANN001
        captured["kwargs"] = kwargs

        def _wrap(fn):
            def _inner(*a, **k):
                captured["called"] = True
                return fn(*a, **k)

            return _inner

        return _wrap

    monkeypatch.setattr(lc, "_real_observe", fake_observe, raising=False)

    @lc.observe(name="rag.query")
    def fn(x: int) -> int:
        return x

    assert fn(7) == 7
    assert captured["called"] is True
    assert captured["kwargs"]["name"] == "rag.query"


def test_close_langfuse_idempotent() -> None:
    lc.close_langfuse()
    lc.close_langfuse()
