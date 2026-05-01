"""T-037 — Email RAG draft (classified email + tenant RAG context → reply)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from app.email_v10.classify import EmailClassification

logger = logging.getLogger(__name__)

__all__ = ["DraftReply", "compose_reply"]


@dataclass(slots=True)
class DraftReply:
    subject: str
    body: str
    citations: list[str]
    confidence: float


_TONE = {
    "urgent": "Acknowledge the urgency, confirm we're investigating, give an ETA, escalate.",
    "billing": "Apologise for any confusion, restate the facts from the invoice context.",
    "tech": "Thank the reporter, state the next debugging step, ask for missing info.",
    "sales": "Thank the lead, share next steps + a calendly slot.",
    "spam": "(do not reply)",
}


def compose_reply(
    *,
    subject: str,
    body: str,
    classification: EmailClassification,
    rag_search: Callable[[str], list[dict]],
    tenant_id: str,
    max_context_chunks: int = 3,
) -> DraftReply:
    if classification.category == "spam":
        return DraftReply(
            subject=f"[spam] {subject}",
            body="(spam — no auto-reply)",
            citations=[],
            confidence=0.0,
        )

    contexts = rag_search(f"{subject}\n{body}")[:max_context_chunks]
    citations: list[str] = []
    context_block: list[str] = []
    for c in contexts:
        ref = str(c.get("id", c.get("payload", {}).get("chunk_id", "")))
        if ref:
            citations.append(ref)
        text = str(c.get("payload", {}).get("text", c.get("text", "")))
        if text:
            context_block.append(f"[{ref}] {text}")

    inline_citations = " ".join(f"[{cid}]" for cid in citations)
    tone = _TONE.get(classification.category, "Professional and helpful tone.")
    reply_body = (
        f"Hi,\n\n{tone}\n\n"
        + ("\n".join(f"> {line}" for line in context_block) + "\n\n" if context_block else "")
        + f"Best regards,\nABS Assistant {inline_citations}".strip()
    )
    confidence = min(1.0, classification.confidence + 0.1 * len(citations))
    logger.info(
        "email_draft tenant=%s category=%s citations=%d conf=%.2f",
        tenant_id,
        classification.category,
        len(citations),
        confidence,
    )
    return DraftReply(
        subject=f"Re: {subject}" if not subject.lower().startswith("re:") else subject,
        body=reply_body,
        citations=citations,
        confidence=confidence,
    )
