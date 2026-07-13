# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Action item ↔ Linear/Jira ticket linker.

Decides between *update existing ticket* vs *create new* via cosine similarity
of embeddings (≥ 0.85 → update). Default backends are mock; real Linear/Jira
clients sit behind deferred imports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from app.meeting.action_items import ActionItem
from app.rag.embedding_bge import cosine, get_embedder

logger = logging.getLogger(__name__)

__all__ = [
    "ExistingTicket",
    "TicketDecision",
    "decide_ticket_action",
    "link_action_items",
]


@dataclass(slots=True)
class ExistingTicket:
    ticket_id: str
    title: str
    embedding: list[float] | None = None


@dataclass(slots=True)
class TicketDecision:
    action: str  # "update" | "create"
    target_id: str | None
    similarity: float
    item: ActionItem
    requires_human_approval: bool = True


_DEFAULT_THRESHOLD = 0.85


def decide_ticket_action(
    item: ActionItem,
    existing: list[ExistingTicket],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    embed: Callable[[str], list[float]] | None = None,
) -> TicketDecision:
    embed_fn = embed or (lambda t: get_embedder().embed_one(t))
    item_vec = embed_fn(item.text)
    best: ExistingTicket | None = None
    best_score = 0.0
    for ticket in existing:
        ticket_vec = ticket.embedding or embed_fn(ticket.title)
        score = cosine(item_vec, ticket_vec)
        if score > best_score:
            best = ticket
            best_score = score
    if best is not None and best_score >= threshold:
        return TicketDecision(
            action="update",
            target_id=best.ticket_id,
            similarity=best_score,
            item=item,
        )
    return TicketDecision(
        action="create",
        target_id=None,
        similarity=best_score,
        item=item,
    )


def link_action_items(
    items: list[ActionItem],
    existing: list[ExistingTicket],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    embed: Callable[[str], list[float]] | None = None,
) -> list[TicketDecision]:
    decisions = [
        decide_ticket_action(item, existing, threshold=threshold, embed=embed)
        for item in items
    ]
    n_updates = sum(1 for d in decisions if d.action == "update")
    n_creates = sum(1 for d in decisions if d.action == "create")
    logger.info(
        "ticket_link items=%d updates=%d creates=%d", len(items), n_updates, n_creates
    )
    return decisions
