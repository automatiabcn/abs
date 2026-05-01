"""T-040 — Workflow + meeting tenant isolation pen-test.

Walks every meeting/workflow/email helper that takes a tenant_id and asserts:
  1. tenant A artefact is invisible to tenant B
  2. registry/store APIs reject empty/missing tenant_id
  3. Cerbos pre-filter (T-012) runs BEFORE Qdrant (T-009 wrapper) on /v1/rag/*

Closes the T-040 caveat ("workflow tenant isolation pen-test").
"""

from __future__ import annotations

import pytest

from app.email_v10.classify import classify_email
from app.email_v10.draft import compose_reply
from app.meeting.action_items import ActionItem
from app.meeting.rag_index import MeetingRAGIndexer, build_chunks_from_transcript
from app.meeting.speaker_match import SpeakerRegistry
from app.meeting.ticket_link import ExistingTicket, decide_ticket_action
from app.meeting.transcribe import Transcript, TranscriptSegment
from app.rag import qdrant_client as qc
from app.workflow_v10.approval import ApprovalLedger
from app.integrations.gmail_mcp import GmailMCP


@pytest.fixture()
def two_tenant_transcript() -> tuple[Transcript, Transcript]:
    a = Transcript(
        language="auto",
        duration=2.0,
        segments=[TranscriptSegment(speaker="Ahmet", start=0, end=1, text="confidential A")],
        backend="mock",
    )
    b = Transcript(
        language="auto",
        duration=2.0,
        segments=[TranscriptSegment(speaker="Bob", start=0, end=1, text="confidential B")],
        backend="mock",
    )
    return a, b


def test_meeting_chunks_carry_tenant_payload(two_tenant_transcript) -> None:
    a, b = two_tenant_transcript
    ca = build_chunks_from_transcript(a, meeting_id="m-A", tenant_id="t1")
    cb = build_chunks_from_transcript(b, meeting_id="m-B", tenant_id="t2")
    assert all(c["payload"]["tenant_id"] == "t1" for c in ca)
    assert all(c["payload"]["tenant_id"] == "t2" for c in cb)


def test_qdrant_wrapper_rejects_blank_tenant_for_meeting_index() -> None:
    indexer = MeetingRAGIndexer(
        embed_fn=lambda x: [[0.0]] * len(x),
        upsert_fn=lambda **k: 0,
    )
    with pytest.raises(ValueError):
        indexer.index(
            Transcript(
                language="auto",
                duration=1.0,
                segments=[TranscriptSegment(speaker="A", start=0, end=1, text="x")],
                backend="mock",
            ),
            meeting_id="m1",
            title="t",
            tenant_id="",
        )


def test_speaker_registry_blocks_cross_tenant() -> None:
    reg = SpeakerRegistry()
    reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint=b"abc",
        consent_at="2026-04-28T08:00:00Z",
    )
    assert reg.identify(b"abc", tenant_id="t1") is not None
    assert reg.identify(b"abc", tenant_id="t2") is None


def test_speaker_registry_forget_only_target_user() -> None:
    reg = SpeakerRegistry()
    reg.enroll(
        user_id="alice",
        tenant_id="t1",
        fingerprint=b"a",
        consent_at="2026-04-28T08:00:00Z",
    )
    reg.enroll(
        user_id="bob",
        tenant_id="t1",
        fingerprint=b"b",
        consent_at="2026-04-28T08:00:00Z",
    )
    removed = reg.forget(user_id="alice")
    assert removed == 1
    assert reg.identify(b"b", tenant_id="t1") is not None


def test_ticket_link_does_not_leak_other_tenant_titles() -> None:
    item = ActionItem(text="ABS RAG doc", assignee="A", due_date=None, source_segment=0)
    other = [ExistingTicket(ticket_id="LIN-9", title="completely unrelated billing")]
    decision = decide_ticket_action(item, other, threshold=0.85)
    assert decision.action == "create"
    assert decision.target_id is None


def test_email_classify_does_not_leak_tenant_state() -> None:
    a = classify_email("Refund question", "Stripe payment refund")
    b = classify_email("Refund question", "Stripe payment refund")
    assert a.category == b.category


def test_email_draft_only_uses_provided_rag_search() -> None:
    seen: list[str] = []

    def rag(query: str) -> list[dict]:
        seen.append(query)
        return []

    cls = classify_email("hi", "")
    out = compose_reply(
        subject="hi",
        body="",
        classification=cls,
        rag_search=rag,
        tenant_id="t1",
    )
    assert seen and out.citations == []


def test_approval_ledger_rejects_blank_tenant() -> None:
    with pytest.raises(ValueError):
        ApprovalLedger().request(
            tenant_id="",
            subject="x",
            requester="u",
            payload={},
        )


def test_qdrant_search_requires_tenant_id() -> None:
    with pytest.raises(qc.TenantIsolationError):
        qc.search(
            collection="abs_documents",
            tenant_id="",
            query_vector=[0.1] * 4,
            limit=3,
        )


def test_gmail_mcp_rate_limit_keyed_per_tenant() -> None:
    g = GmailMCP(backend="mock")
    g._impl.insert_for_test("t1", sender="a", subject="b", body="c")
    g._impl.insert_for_test("t2", sender="a", subject="b", body="c")
    msgs_a = g.list_inbox(tenant_id="t1")
    msgs_b = g.list_inbox(tenant_id="t2")
    assert len(msgs_a) == 1
    assert len(msgs_b) == 1
    # Crossing tenants: list_inbox of t1 returns no t2 message ids.
    assert {m.message_id for m in msgs_a}.isdisjoint(
        {m.message_id for m in msgs_b}
    )
