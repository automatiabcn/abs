"""T-037 — Email RAG draft tests."""

from __future__ import annotations

from app.email_v10.classify import EmailClassification, classify_email
from app.email_v10.draft import compose_reply


def _rag(query: str) -> list[dict]:
    return [
        {
            "id": "doc-1",
            "payload": {
                "chunk_id": "doc-1",
                "text": "Refund policy: full refund within 14 days.",
            },
        }
    ]


def test_draft_reply_includes_citation_marker() -> None:
    cls = classify_email("Refund question", "Can I refund my purchase?")
    out = compose_reply(
        subject="Refund question",
        body="Can I refund my purchase?",
        classification=cls,
        rag_search=_rag,
        tenant_id="t1",
    )
    assert "[doc-1]" in out.body
    assert "doc-1" in out.citations


def test_draft_subject_re_prefix() -> None:
    cls = classify_email("Hello", "")
    out = compose_reply(
        subject="Hello",
        body="",
        classification=cls,
        rag_search=lambda q: [],
        tenant_id="t1",
    )
    assert out.subject == "Re: Hello"


def test_draft_does_not_double_re_prefix() -> None:
    cls = classify_email("Re: Hello", "")
    out = compose_reply(
        subject="Re: Hello",
        body="",
        classification=cls,
        rag_search=lambda q: [],
        tenant_id="t1",
    )
    assert out.subject == "Re: Hello"


def test_spam_classification_returns_no_reply_marker() -> None:
    cls = EmailClassification(
        category="spam", priority=-10, confidence=0.9, reasons=["winner"]
    )
    out = compose_reply(
        subject="winner",
        body="click here",
        classification=cls,
        rag_search=lambda q: [],
        tenant_id="t1",
    )
    assert out.body.startswith("(spam")
    assert out.confidence == 0.0


def test_no_context_still_produces_body() -> None:
    cls = classify_email("Quick check", "Hello")
    out = compose_reply(
        subject="Quick check",
        body="Hello",
        classification=cls,
        rag_search=lambda q: [],
        tenant_id="t1",
    )
    assert "Hi" in out.body
    assert out.citations == []
