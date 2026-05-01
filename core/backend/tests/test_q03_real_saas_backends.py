"""T-Q03 — respx-mocked unit tests for the real-API SaaS backends.

We never hit the live providers. respx intercepts the httpx client so the
tests assert request shape (URL, headers, payload) and verify that the
returned dataclasses are populated from the mock JSON responses.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.integrations.gmail_mcp import GmailMCP, GmailTokenVault, _GoogleBackend
from app.meeting.bot_recall import _RecallBackend
from app.meeting.transcribe import _DeepgramBackend
from app.meeting.tts_reminder import _ElevenLabsBackend


# ─── Recall.ai ────────────────────────────────────────────────────────────


@respx.mock
def test_recall_schedule_calls_api_and_returns_bot_job() -> None:
    backend = _RecallBackend(api_key="rk_test_abc")
    route = respx.post("https://api.recall.ai/api/v1/bot").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "bot_abc",
                "status": "scheduled",
                "created_at": "2026-04-28T10:00:00Z",
            },
        )
    )
    job = backend.schedule(
        meeting_url="https://meet.example/x",
        tenant_id="acme",
        cost_estimate_usd=0.5,
        metadata={"k": "v"},
    )
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Token rk_test_abc"
    assert b"meet.example/x" in sent.content
    assert job.bot_id == "bot_abc"
    assert job.status == "scheduled"


@respx.mock
def test_recall_status_round_trip() -> None:
    backend = _RecallBackend(api_key="rk_test_abc")
    respx.get("https://api.recall.ai/api/v1/bot/bot_abc").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "bot_abc",
                "status": "completed",
                "meeting_url": "https://meet.example/x",
                "metadata": {"abs_tenant": "acme"},
                "transcript_url": "https://recall.example/t.txt",
            },
        )
    )
    job = backend.status("bot_abc")
    assert job.bot_id == "bot_abc"
    assert job.status == "completed"
    assert job.transcript_path == "https://recall.example/t.txt"


@respx.mock
def test_recall_cancel_calls_delete() -> None:
    backend = _RecallBackend(api_key="rk_test_abc")
    route = respx.delete("https://api.recall.ai/api/v1/bot/bot_abc").mock(
        return_value=httpx.Response(204)
    )
    backend.cancel("bot_abc")
    assert route.called


# ─── Deepgram ─────────────────────────────────────────────────────────────


@respx.mock
def test_deepgram_transcribe_parses_diarized_words(tmp_path: Path) -> None:
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"RIFF....mock....")
    backend = _DeepgramBackend(api_key="dg_test_abc")
    route = respx.post("https://api.deepgram.com/v1/listen").mock(
        return_value=httpx.Response(
            200,
            json={
                "metadata": {"duration": 4.5, "language": "en"},
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "words": [
                                        {
                                            "word": "hi",
                                            "punctuated_word": "Hi.",
                                            "start": 0.0,
                                            "end": 0.5,
                                            "speaker": 0,
                                        },
                                        {
                                            "word": "world",
                                            "punctuated_word": "World",
                                            "start": 0.6,
                                            "end": 1.2,
                                            "speaker": 1,
                                        },
                                    ]
                                }
                            ]
                        }
                    ]
                },
            },
        )
    )
    transcript = backend.transcribe(audio)
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Token dg_test_abc"
    assert sent.headers["Content-Type"] == "audio/wav"
    assert transcript.duration == pytest.approx(4.5)
    assert len(transcript.segments) == 2
    assert transcript.segments[0].speaker == "speaker_0"
    assert transcript.segments[1].speaker == "speaker_1"


# ─── ElevenLabs ───────────────────────────────────────────────────────────


@respx.mock
def test_elevenlabs_writes_mp3_bytes(tmp_path: Path) -> None:
    backend = _ElevenLabsBackend(api_key="el_test_abc", voice_id="voice_1")
    fake_audio = b"\x00\x01\x02fake-mp3"
    route = respx.post(
        "https://api.elevenlabs.io/v1/text-to-speech/voice_1"
    ).mock(return_value=httpx.Response(200, content=fake_audio))
    out = backend.synthesize("Merhaba dünya", target_dir=tmp_path)
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["xi-api-key"] == "el_test_abc"
    assert b'"eleven_multilingual_v2"' in sent.content
    assert Path(out.audio_path).read_bytes() == fake_audio
    assert Path(out.audio_path).suffix == ".mp3"


# ─── Gmail (google backend) ───────────────────────────────────────────────


def _make_gmail() -> GmailMCP:
    vault = GmailTokenVault()
    vault.store(tenant_id="acme", refresh_token="rt-refresh", scope="gmail.modify")
    # Bypass the real httpx import + module-level settings so credentials are
    # supplied via attribute injection.
    return GmailMCP(backend="google", vault=vault)


@respx.mock
def test_gmail_list_uses_oauth_refresh_and_lists_messages(monkeypatch) -> None:
    from app import config as _cfg

    monkeypatch.setattr(_cfg.settings, "gmail_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(
        _cfg.settings, "gmail_oauth_client_secret", "csec", raising=False
    )
    mcp = _make_gmail()
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "ya29.test", "expires_in": 3600}
        )
    )
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(
            200, json={"messages": [{"id": "m1"}]}
        )
    )
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "snippet": "hello",
                "labelIds": ["INBOX"],
                "internalDate": "1700000000000",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "a@x"},
                        {"name": "To", "value": "b@y"},
                        {"name": "Subject", "value": "Test"},
                    ]
                },
            },
        )
    )
    msgs = mcp.list_inbox(tenant_id="acme", limit=5)
    assert len(msgs) == 1
    assert msgs[0].subject == "Test"
    assert msgs[0].sender == "a@x"
    assert "INBOX" in msgs[0].labels


@respx.mock
def test_gmail_backend_requires_oauth_credentials() -> None:
    vault = GmailTokenVault()
    vault.store(tenant_id="acme", refresh_token="rt", scope="gmail.modify")
    backend = _GoogleBackend(vault)
    with pytest.raises(RuntimeError, match="OAuth client credentials missing"):
        backend._access_token("acme")
