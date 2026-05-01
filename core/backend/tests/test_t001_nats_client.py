"""T-001 — NATS client wrapper unit tests (no live broker required)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("nats")

from app.event_bus import nats_client as nc  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nc, "_nc", None)
    monkeypatch.setattr(nc, "_js", None)


def _stub_jetstream(monkeypatch: pytest.MonkeyPatch, mock_js: AsyncMock) -> None:
    async def _fake() -> AsyncMock:
        return mock_js

    monkeypatch.setattr(nc, "get_jetstream", _fake)


async def test_publish_encodes_dict_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_js = AsyncMock()
    mock_js.publish.return_value = SimpleNamespace(seq=42)
    _stub_jetstream(monkeypatch, mock_js)

    seq = await nc.publish("subject.x", {"a": 1, "b": "y"})

    assert seq == 42
    args, kwargs = mock_js.publish.call_args
    assert args[0] == "subject.x"
    assert args[1] == json.dumps({"a": 1, "b": "y"}, separators=(",", ":")).encode()
    assert kwargs.get("headers") is None
    assert "stream" not in kwargs


async def test_publish_passes_bytes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_js = AsyncMock()
    mock_js.publish.return_value = SimpleNamespace(seq=7)
    _stub_jetstream(monkeypatch, mock_js)

    seq = await nc.publish("s", b"raw", headers={"x-tenant": "t1"}, stream="EVT")

    assert seq == 7
    args, kwargs = mock_js.publish.call_args
    assert args[1] == b"raw"
    assert kwargs == {"headers": {"x-tenant": "t1"}, "stream": "EVT"}


async def test_ensure_stream_idempotent_on_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nats.js.errors import BadRequestError

    mock_js = AsyncMock()
    mock_js.add_stream.side_effect = BadRequestError(
        description="stream name already in use"
    )
    _stub_jetstream(monkeypatch, mock_js)

    await nc.ensure_stream("EVT", ["evt.>"])

    mock_js.update_stream.assert_awaited_once()
    config = mock_js.update_stream.call_args.args[0]
    assert config.name == "EVT"
    assert list(config.subjects) == ["evt.>"]


async def test_ensure_stream_reraises_unknown_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nats.js.errors import BadRequestError

    mock_js = AsyncMock()
    mock_js.add_stream.side_effect = BadRequestError(description="invalid subject")
    _stub_jetstream(monkeypatch, mock_js)

    with pytest.raises(BadRequestError):
        await nc.ensure_stream("EVT", ["bad subject"])

    mock_js.update_stream.assert_not_awaited()


async def test_subscribe_handler_acks_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_subscribe(subject, **kwargs):  # noqa: ANN001
        captured["subject"] = subject
        captured["kwargs"] = kwargs
        return MagicMock()

    mock_js = AsyncMock()
    mock_js.subscribe = fake_subscribe
    _stub_jetstream(monkeypatch, mock_js)

    seen: list[bytes] = []

    async def handler(msg):  # noqa: ANN001
        seen.append(msg.data)

    await nc.subscribe("evt.x", handler, durable="d1", queue="q1")

    msg = MagicMock()
    msg.data = b'{"x":1}'
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await captured["kwargs"]["cb"](msg)

    assert seen == [b'{"x":1}']
    msg.ack.assert_awaited_once()
    msg.nak.assert_not_awaited()
    assert captured["kwargs"]["durable"] == "d1"
    assert captured["kwargs"]["queue"] == "q1"
    assert captured["kwargs"]["manual_ack"] is True


async def test_subscribe_handler_naks_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_subscribe(subject, **kwargs):  # noqa: ANN001
        captured["kwargs"] = kwargs
        return MagicMock()

    mock_js = AsyncMock()
    mock_js.subscribe = fake_subscribe
    _stub_jetstream(monkeypatch, mock_js)

    async def boom(msg):  # noqa: ANN001
        raise ValueError("nope")

    await nc.subscribe("evt.fail", boom)

    msg = MagicMock()
    msg.data = b"{}"
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await captured["kwargs"]["cb"](msg)

    msg.nak.assert_awaited_once()
    msg.ack.assert_not_awaited()


async def test_close_idempotent_when_unconnected() -> None:
    await nc.close()
    await nc.close()


async def test_close_drains_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_nc = AsyncMock()
    fake_nc.is_connected = True
    monkeypatch.setattr(nc, "_nc", fake_nc)
    monkeypatch.setattr(nc, "_js", MagicMock())

    await nc.close()

    fake_nc.drain.assert_awaited_once()
    fake_nc.close.assert_awaited_once()
    assert nc._nc is None
    assert nc._js is None
