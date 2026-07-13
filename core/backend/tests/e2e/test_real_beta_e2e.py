"""T-R08 — Real beta E2E for the `acme-test` tenant.

Walks the full beta journey end to end using the real code paths:

  1. Load the `acme-test` tenant fixture (RAG corpus + Gmail seed +
     Recall meeting transcript + expected acceptance assertions).
  2. Build a meeting transcript via the mock transcribe backend.
  3. Extract action items + link them to existing tickets.
  4. Index meeting chunks under the acme-test tenant.
  5. Drive Gmail MCP: store OAuth refresh token in the vault, seed an
     inbox message, draft a reply, send it, label the original thread.
  6. Drive Recall.ai bot: schedule under the daily budget, confirm the
     stored job carries the correct tenant tag.

Stripe is intentionally **not** part of this flow — beta participants
opt in without billing; their pricing UI was already gated by
`NEXT_PUBLIC_BILLING_ENABLED=false` in T-R03.

The Qdrant store is the in-process mock backend, so this test runs
inside CI without external services. The Gmail and Recall paths use
their `mock` backends; the `_GoogleBackend` and `_RecallBackend`
classes are exercised by their own respx-mocked unit tests (T-Q03).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.integrations.gmail_mcp import GmailMCP, GmailTokenVault
from app.meeting.action_items import extract_action_items
from app.meeting.bot_recall import MeetingBot
from app.meeting.rag_index import MeetingRAGIndexer, build_chunks_from_transcript
from app.meeting.ticket_link import ExistingTicket, link_action_items
from app.meeting.transcribe import Transcriber


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "acme_test_tenant.json"


@pytest.fixture(scope="module")
def acme() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_acme_fixture_shape(acme: dict) -> None:
    assert acme["tenant_id"] == "acme-test"
    assert len(acme["rag_corpus"]) >= 2
    assert acme["gmail"]["oauth_refresh_token"].startswith("1//0sandbox")
    assert acme["recall"]["meeting_url"].startswith("https://meet.google.com/")


def test_meeting_round_trip_for_acme(acme: dict) -> None:
    """Recall transcript → action items → tickets → RAG chunks."""
    transcript = Transcriber("mock").transcribe(acme["recall"]["transcript_seed"])
    assert transcript.segments, "mock transcribe must yield segments"

    items = extract_action_items(transcript)
    assert items, "expected at least one action item from acme transcript"

    # Acceptance: assignees from fixture appear in extracted items.
    assignees = {it.assignee for it in items}
    expected = set(acme["expected"]["action_item_assignees_subset"])
    assert expected & assignees, f"missing expected assignees {expected - assignees}"

    existing = [
        ExistingTicket(ticket_id="LIN-ACME-1", title="Sözleşmeyi bu hafta gönder")
    ]
    decisions = link_action_items(items, existing)
    assert decisions, "ticket linking must yield at least one decision"
    assert {d.action for d in decisions} <= {"create", "update", "skip"}

    chunks = build_chunks_from_transcript(
        transcript,
        meeting_id="acme-q3-okr-sync",
        title="Acme Q3 OKR sync",
        tenant_id=acme["tenant_id"],
    )
    assert chunks, "transcript must produce at least one RAG chunk"
    assert all(c["payload"]["tenant_id"] == acme["tenant_id"] for c in chunks)


def test_meeting_rag_index_isolates_tenant(acme: dict) -> None:
    """RAG indexer must tag every Qdrant point with tenant_id=acme-test."""
    transcript = Transcriber("mock").transcribe(acme["recall"]["transcript_seed"])

    upserted: list[dict] = []
    ensured: list[str] = []

    def fake_embed(texts):  # noqa: ANN001
        return [[0.05, 0.10, 0.15, 0.20] for _ in texts]

    def fake_upsert(*, collection: str, tenant_id: str, points) -> int:  # noqa: ANN001
        for p in points:
            upserted.append({"collection": collection, "tenant_id": tenant_id, **p})
        return len(points)

    def fake_ensure(collection: str) -> None:
        ensured.append(collection)

    indexer = MeetingRAGIndexer(
        embed_fn=fake_embed,
        upsert_fn=fake_upsert,
        ensure_fn=fake_ensure,
    )
    n = indexer.index(
        transcript,
        meeting_id="acme-q3-okr-sync",
        title="Acme Q3 OKR sync",
        tenant_id=acme["tenant_id"],
    )
    assert n == len(upserted) > 0
    assert ensured == ["abs_meetings"]
    assert all(p["tenant_id"] == "acme-test" for p in upserted)
    assert all(p["payload"]["tenant_id"] == "acme-test" for p in upserted)


def test_gmail_mcp_full_flow_for_acme(acme: dict) -> None:
    """Vault → seed → list → draft → send → label, all under acme-test."""
    vault = GmailTokenVault()
    vault.store(
        tenant_id=acme["tenant_id"],
        refresh_token=acme["gmail"]["oauth_refresh_token"],
        scope=acme["gmail"]["scope"],
    )
    assert vault.get(acme["tenant_id"])["scope"] == acme["gmail"]["scope"]

    mcp = GmailMCP(backend="mock", vault=vault)
    backend = mcp._impl  # type: ignore[attr-defined]
    seeded = []
    for seed in acme["gmail"]["seed_inbox"]:
        msg = backend.insert_for_test(  # type: ignore[attr-defined]
            acme["tenant_id"],
            sender=seed["sender"],
            subject=seed["subject"],
            body=seed["body"],
        )
        seeded.append(msg)

    inbox = mcp.list_inbox(tenant_id=acme["tenant_id"], limit=10)
    assert len(inbox) == len(seeded)

    target = inbox[0]
    draft_id = mcp.draft_reply(
        tenant_id=acme["tenant_id"],
        thread_id=target.thread_id,
        subject=f"Re: {target.subject}",
        body="Teşekkürler — fiyat tablosu PDF olarak ekte. Discovery için takvim linki: https://cal.acme/disco",
    )
    assert draft_id.startswith("draft-")

    sent_id = mcp.send(tenant_id=acme["tenant_id"], draft_id=draft_id)
    assert sent_id.startswith("sent-")

    mcp.label(
        tenant_id=acme["tenant_id"],
        message_id=target.message_id,
        add=["abs/replied", "abs/beta"],
    )
    relisted = mcp.list_inbox(tenant_id=acme["tenant_id"], limit=10)
    labelled = [m for m in relisted if m.message_id == target.message_id][0]
    assert "abs/replied" in labelled.labels
    assert "abs/beta" in labelled.labels


def test_recall_bot_schedule_for_acme(acme: dict) -> None:
    """Mock Recall backend: schedule a 30-min bot under the daily cap."""
    bot = MeetingBot(backend_name="mock")
    job = bot.schedule(
        meeting_url=acme["recall"]["meeting_url"],
        tenant_id=acme["tenant_id"],
        duration_minutes=int(acme["recall"]["duration_minutes"]),
        metadata={"source": "T-R08-beta-E2E"},
    )
    assert job.tenant_id == acme["tenant_id"]
    assert job.meeting_url == acme["recall"]["meeting_url"]
    # 30 min × $0.50/h = $0.25 — well under the $50/day cap.
    assert 0.20 < job.estimated_cost_usd < 0.30
    assert job.status == "scheduled"

    # Status round-trip pulls the same record back.
    refetched = bot.status(job.bot_id)
    assert refetched.bot_id == job.bot_id
    assert refetched.metadata["source"] == "T-R08-beta-E2E"
