"""T-035 — Gmail MCP wrapper tests."""

from __future__ import annotations

import pytest

from app.integrations.gmail_mcp import (
    GmailMCP,
    GmailQuotaExceeded,
    GmailTokenVault,
)


def test_token_vault_round_trip() -> None:
    v = GmailTokenVault()
    v.store(tenant_id="t1", refresh_token="abc", scope="gmail.readonly")
    tok = v.get("t1")
    assert tok["refresh_token"] == "abc"
    assert v.revoke("t1") is True
    with pytest.raises(KeyError):
        v.get("t1")


def test_token_vault_requires_inputs() -> None:
    v = GmailTokenVault()
    with pytest.raises(ValueError):
        v.store(tenant_id="", refresh_token="abc", scope="x")
    with pytest.raises(ValueError):
        v.store(tenant_id="t1", refresh_token="", scope="x")


def test_list_inbox_returns_seeded_messages() -> None:
    g = GmailMCP(backend="mock")
    g._impl.insert_for_test(
        "t1", sender="a@b.c", subject="Q3 invoice question", body="hello"
    )
    msgs = g.list_inbox(tenant_id="t1")
    assert len(msgs) == 1
    assert msgs[0].sender == "a@b.c"


def test_draft_and_send_round_trip() -> None:
    g = GmailMCP(backend="mock")
    msg = g._impl.insert_for_test("t1", sender="a@b.c", subject="hi", body="body")
    draft = g.draft_reply(
        tenant_id="t1", thread_id=msg.thread_id, subject="re", body="reply"
    )
    sent = g.send(tenant_id="t1", draft_id=draft)
    assert draft.startswith("draft-")
    assert sent.startswith("sent-")


def test_label_adds_and_removes() -> None:
    g = GmailMCP(backend="mock")
    msg = g._impl.insert_for_test("t1", sender="a@b.c", subject="hi", body="body")
    g.label(tenant_id="t1", message_id=msg.message_id, add=["urgent"])
    g.label(
        tenant_id="t1",
        message_id=msg.message_id,
        add=["abs/processed"],
        remove=["urgent"],
    )
    after = g._impl.get("t1", msg.message_id)
    assert after.labels == ["abs/processed"]


def test_rate_limit_blocks_excessive_send() -> None:
    g = GmailMCP(backend="mock")
    msg = g._impl.insert_for_test("t1", sender="a", subject="b", body="c")
    draft = g.draft_reply(
        tenant_id="t1", thread_id=msg.thread_id, subject="r", body="r"
    )
    with pytest.raises(GmailQuotaExceeded):
        for _ in range(4):
            g.send(tenant_id="t1", draft_id=draft)


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        GmailMCP(backend="nope")


def test_google_backend_imports_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-Q03: backend now uses Gmail REST via httpx. Missing httpx must
    surface a clean ImportError; valid construction must succeed."""
    import sys

    # Successful path — httpx present, refresh token stored.
    mcp = GmailMCP(backend="google")
    assert mcp.backend == "google"

    # Missing-httpx path — backend init raises ImportError.
    monkeypatch.setitem(sys.modules, "httpx", None)
    with pytest.raises(ImportError):
        GmailMCP(backend="google")
