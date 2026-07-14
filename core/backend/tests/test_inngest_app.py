"""Inngest function registration + NATS bridge tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("inngest")

import inngest  # noqa: E402

from app.worker import inngest_app, nats_bridge  # noqa: E402


def test_on_user_registered_metadata_registered() -> None:
    cfg = inngest_app.on_user_registered.get_config("http://localhost").main
    assert cfg.id == "abs-backend-on_user_registered"
    assert cfg.triggers[0].event == "abs/user.registered"
    assert cfg.steps["step"].retries.attempts == 4


def test_functions_export_contains_handler() -> None:
    assert inngest_app.on_user_registered in inngest_app.functions


def test_inngest_client_app_id() -> None:
    assert inngest_app.inngest_client.app_id == "abs-backend"


def test_default_subject_map_covers_user_lifecycle() -> None:
    keys = nats_bridge.DEFAULT_SUBJECT_MAP
    assert keys["abs.events.user.registered"] == "abs/user.registered"
    assert keys["abs.events.user.login.success"] == "abs/user.login.success"
    assert keys["abs.events.user.login.failed"] == "abs/user.login.failed"


def test_decode_rejects_non_json() -> None:
    with pytest.raises(ValueError):
        nats_bridge._decode(b"not-json")


def test_decode_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        nats_bridge._decode(json.dumps([1, 2]).encode())


def test_decode_returns_dict() -> None:
    out = nats_bridge._decode(json.dumps({"a": 1}).encode())
    assert out == {"a": 1}


async def test_bridge_forwards_event_to_inngest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_handlers: dict[str, callable] = {}

    async def fake_ensure_stream(name, subjects, **_):  # noqa: ANN001
        captured_handlers["stream"] = (name, subjects)

    async def fake_subscribe(subject, handler, *, durable, **_):  # noqa: ANN001
        captured_handlers[subject] = handler
        captured_handlers[f"{subject}::durable"] = durable
        return MagicMock()

    monkeypatch.setattr(nats_bridge, "ensure_stream", fake_ensure_stream)
    monkeypatch.setattr(nats_bridge, "subscribe", fake_subscribe)

    sent: list[inngest.Event] = []

    async def fake_send(event):  # noqa: ANN001
        sent.append(event)

    monkeypatch.setattr(nats_bridge.inngest_client, "send", fake_send)

    subs = await nats_bridge.bridge_nats_to_inngest()
    assert len(subs) == 3
    assert captured_handlers["stream"] == ("ABS_EVENTS", ["abs.events.>"])
    assert (
        captured_handlers["abs.events.user.registered::durable"]
        == "abs-bridge-abs_user_registered"
    )

    handler = captured_handlers["abs.events.user.registered"]
    msg = MagicMock()
    msg.subject = "abs.events.user.registered"
    msg.data = json.dumps({"user_id": "u1", "email": "a@b.c"}).encode()
    await handler(msg)

    assert len(sent) == 1
    assert sent[0].name == "abs/user.registered"
    assert sent[0].data == {"user_id": "u1", "email": "a@b.c"}


async def test_bridge_propagates_decode_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_ensure_stream(*a, **k):  # noqa: ANN001
        return None

    async def fake_subscribe(subject, handler, **_):  # noqa: ANN001
        captured[subject] = handler
        return MagicMock()

    monkeypatch.setattr(nats_bridge, "ensure_stream", fake_ensure_stream)
    monkeypatch.setattr(nats_bridge, "subscribe", fake_subscribe)
    monkeypatch.setattr(nats_bridge.inngest_client, "send", AsyncMock())

    await nats_bridge.bridge_nats_to_inngest(
        subject_map={"abs.events.user.registered": "abs/user.registered"}
    )
    handler = captured["abs.events.user.registered"]

    bad_msg = MagicMock()
    bad_msg.data = b"oops"
    with pytest.raises(ValueError):
        await handler(bad_msg)
