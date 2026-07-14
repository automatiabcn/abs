"""MLX provider tests (respx mock, real bridge not required)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.providers.mlx import MLXProvider
from app.providers.schemas import ProviderError


@pytest.mark.asyncio
async def test_mlx_no_url_raises_provider_error(monkeypatch):
    monkeypatch.setattr(settings, "mlx_url", "")
    with pytest.raises(ProviderError) as exc:
        await MLXProvider().call("hi")
    assert exc.value.transient is False
    assert "MLX_URL" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_mlx_success_response_parsed(monkeypatch):
    monkeypatch.setattr(settings, "mlx_url", "http://localhost:11436")
    respx.post("http://localhost:11436/v1/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": "hello",
                "prompt_tokens": 3,
                "completion_tokens": 1,
            },
        )
    )
    resp = await MLXProvider().call("ping")
    assert resp.text == "hello"
    assert resp.model == "llama3-8b"
    assert resp.provider == "mlx"
    assert resp.tokens_in == 3
    assert resp.tokens_out == 1


@pytest.mark.asyncio
@respx.mock
async def test_mlx_error_field_raises_transient(monkeypatch):
    monkeypatch.setattr(settings, "mlx_url", "http://localhost:11436")
    respx.post("http://localhost:11436/v1/generate").mock(
        return_value=httpx.Response(200, json={"error": "OOM", "response": ""})
    )
    with pytest.raises(ProviderError) as exc:
        await MLXProvider().call("heavy", model="llama3-8b")
    assert exc.value.transient is True
    assert "OOM" in str(exc.value)
