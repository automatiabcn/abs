"""Provider validator mocks."""

from __future__ import annotations

import httpx

from app.smart_link import provider_validators as pv


class _FakeRsp:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def _patch_get(monkeypatch, url_substr: str, status_code: int = 200):
    def _get(self, url, *args, **kwargs):
        if url_substr in str(url):
            return _FakeRsp(status_code, {"data": []})
        raise httpx.RequestError(f"unexpected url {url}")

    monkeypatch.setattr(httpx.Client, "get", _get)


def _patch_post(monkeypatch, url_substr: str, status_code: int = 200):
    def _post(self, url, *args, **kwargs):
        if url_substr in str(url):
            return _FakeRsp(status_code, {"id": "msg_x"})
        raise httpx.RequestError(f"unexpected url {url}")

    monkeypatch.setattr(httpx.Client, "post", _post)


def test_openai_ok_when_200(monkeypatch):
    _patch_get(monkeypatch, "api.openai.com/v1/models", 200)
    out = pv.validate_openai("sk-test-12345")
    assert out["ok"] is True
    assert out["error"] is None


def test_anthropic_treats_400_as_valid_key(monkeypatch):
    """Anthropic /messages with bad payload returns 400 → key valid."""
    _patch_post(monkeypatch, "api.anthropic.com/v1/messages", 400)
    out = pv.validate_anthropic("sk-ant-test-key")
    assert out["ok"] is True


def test_anthropic_401_means_invalid_key(monkeypatch):
    _patch_post(monkeypatch, "api.anthropic.com/v1/messages", 401)
    out = pv.validate_anthropic("sk-ant-bad")
    assert out["ok"] is False
    assert "Invalid" in out["error"]


def test_cohere_groq_gemini_ok(monkeypatch):
    real_get = httpx.Client.get

    def _get(self, url, *args, **kwargs):
        url_str = str(url)
        if "cohere.ai" in url_str or "groq.com" in url_str or "googleapis" in url_str:
            return _FakeRsp(200, {"models": []})
        return real_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", _get)
    assert pv.validate_cohere("co-test")["ok"] is True
    assert pv.validate_groq("gsk-test")["ok"] is True
    assert pv.validate_gemini("gem-test")["ok"] is True


def test_validate_dispatches_by_provider(monkeypatch):
    _patch_get(monkeypatch, "openai.com", 200)
    out = pv.validate("openai", "sk-x")
    assert out["ok"] is True

    out2 = pv.validate("unknown_provider", "x")
    assert out2["ok"] is False
    assert "Unknown provider" in out2["error"]
