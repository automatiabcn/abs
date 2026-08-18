# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Disagreement detector — ask N providers in parallel, measure how far apart
their answers are.

This is the first concrete form of the uncertainty flag the pivot document
lists as differentiator #3: several models, and when they part ways the reader
is told, instead of being handed one confident answer with the doubt removed.

Similarity comes from Cohere embeddings when Cohere is configured, and from a
word-level Jaccard overlap when it is not: crude, but it needs no provider of
its own, so the detector never goes blind just because embeddings are down.

**It runs on the caller's own keys.** Until 08-02 it did not: three providers
were hard-coded and the call reached the adapter with no key attached, so the
developer who had pasted an Anthropic key and asked for a second opinion was
told nobody answered. That is exactly the failure ``app/providers/byok.py``
exists to prevent — a promotion the credential never keeps. The provider list
now comes from what this caller can really reach, and the key travels with the
call.

Three outcomes, and the middle one is the one worth naming:

* ``ok`` — two or more answered, so there is a comparison to report;
* ``single`` — exactly one answered. Zero answers already said "this is not
  agreement"; one answer used to say nothing at all, and that is the more
  convincing lie, because a lone opinion arrives where two were asked for;
* ``empty`` — nobody answered.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.pipelines.execution import run_parallel_named
from app.providers.byok import byok_providers, owner_key_for
from app.providers.cascade import get_active_providers
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

# Preferred first, for two reasons: free, and from different families —
# agreement between siblings proves little. Whatever else the caller has is
# used as well; this only decides who goes first.
PREFERRED: List[Tuple[str, str]] = [
    ("groq", "openai/gpt-oss-120b"),
    ("cloudflare", "@cf/moonshotai/kimi-k2.5"),
    ("cerebras", "gpt-oss-120b"),
]

# Kept for anything that pinned the old shape. Selection no longer reads it.
DEFAULT_MODELS: List[Tuple[str, str, str]] = [(p, p, m) for p, m in PREFERRED]

WANTED = 3

# The last run, per tenant, so `/api/disagreement/latest` can show something
# that happened instead of a placeholder. In memory on purpose: this is a
# readout of the current session, not a record anyone should rely on, and a
# restart honestly reports nothing rather than something stale.
_last: Dict[str, Dict] = {}


def last_run(tenant_id: Optional[str] = None) -> Optional[Dict]:
    return _last.get(tenant_id or "default")


def choose_models(
    tenant_id: Optional[str] = None,
    user_subject: Optional[str] = None,
    limit: Optional[int] = WANTED,
) -> List[Tuple[str, str, Optional[str]]]:
    """Up to three providers this caller can really reach, best-known first.

    A provider appears at most once: two answers from one provider would be a
    single opinion wearing two names, and the independence of the sources is
    the only thing that makes the number mean anything.
    """
    mine = byok_providers(tenant_id, user_subject)
    try:
        usable = list(get_active_providers(extra_configured=mine))
        # A second opinion is not worth spending the operator's paid key on
        # without being asked (app/providers/paid_access).
        from app.providers.paid_access import restrict_chain

        usable = restrict_chain(usable, mine, user_subject)
    except Exception:  # noqa: BLE001 — a bad readout must not kill the feature
        usable = [p for p, _ in PREFERRED]

    # A provider known to be answering nothing right now is not a second
    # opinion, it is a silent chair. On 2026-08-18 the three preferred were
    # asked, two were dead (payment required; a retired model), and gemini and
    # cohere — alive, configured — were never asked: status "single". Known-dead
    # providers go to the END of the order, so the live ones are asked first
    # and the dead ones only if nothing else is left.
    try:
        from app.cascade import provider_health as _health

        dead = {p for p in usable if _health.degraded_reason(p, tenant_id)}
    except Exception:  # noqa: BLE001
        dead = set()

    ordered: List[str] = []
    for name in [p for p, _ in PREFERRED] + list(usable):
        if name in usable and name not in ordered and name not in dead:
            ordered.append(name)
    for name in usable:
        if name in dead and name not in ordered:
            ordered.append(name)

    known = dict(PREFERRED)
    # `None` means "that provider's own default model". Asking a provider for a
    # model belonging to a different one is how a perfectly good key returns 404.
    return [(n, n, known.get(n)) for n in (ordered if limit is None else ordered[:limit])]


def _jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"\w+", a.lower()))
    tb = set(re.findall(r"\w+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def ask_disagree(
    prompt: str,
    analyzer_model: str | None = None,
    *,
    tenant_id: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> Dict:
    """Ask the caller's providers in parallel and score how much they agree.

    Asked in waves: the first WANTED candidates together; if fewer than two
    answered, the next candidates, until two opinions exist or nobody is
    left. A comparison needs two voices, and stopping at the first three
    names when two of them were dead is how "second opinion" became "single".
    """
    candidates = choose_models(tenant_id, user_subject, limit=None)
    asked: List[str] = []
    responses: Dict[str, str] = {}

    async def _wave(batch):
        coros = {}
        for name, prov, mdl in batch:
            key = owner_key_for(prov, tenant_slug=tenant_id, user_subject=user_subject)
            kwargs = {"api_key": key} if key else {}
            # A reasoning model needs room to think AND answer; the room is
            # per model, not one number for everyone.
            kwargs["max_tokens"] = 2048 if (mdl and "kimi" in mdl) else 1024
            try:
                provider = get_provider(prov)
            except KeyError:
                # A name in the chain the registry does not know is a silent
                # chair, not a crash of the whole comparison.
                asked.append(name)
                responses[name] = ""
                continue
            coros[name] = provider.call(prompt, model=mdl, **kwargs)
        raw = await run_parallel_named(coros)
        for name, r in raw.items():
            asked.append(name)
            if isinstance(r, BaseException):
                responses[name] = ""
            else:
                responses[name] = getattr(r, "text", "") or ""

    pos = 0
    while pos < len(candidates):
        batch = candidates[pos : pos + WANTED] if pos == 0 else candidates[pos : pos + 2]
        pos += len(batch)
        await _wave(batch)
        if len([n for n, t in responses.items() if t]) >= 2:
            break

    ok_names = [n for n, t in responses.items() if t]

    # Cosine over Cohere embeddings, else the Jaccard fallback. Which one ran
    # is reported rather than assumed: the footnote used to claim Jaccard on
    # every run, including the ones that used embeddings.
    sim_matrix: List[List[float]] = []
    basis = "none"
    try:
        cohere = get_provider("cohere")
        if not hasattr(cohere, "embed"):
            raise AttributeError("no embed")
        embeds: Dict[str, List[float]] = {}
        for n in ok_names:
            try:
                embeds[n] = await cohere.embed(responses[n])  # type: ignore[attr-defined]
            except Exception:
                embeds[n] = []
        if len(ok_names) > 1 and all(embeds.get(n) for n in ok_names):
            for a in ok_names:
                row = [_cosine(embeds[a], embeds[b]) for b in ok_names]
                sim_matrix.append(row)
            basis = "embedding"
    except Exception:
        pass

    if not sim_matrix and len(ok_names) > 1:
        for a in ok_names:
            row = [_jaccard(responses[a], responses[b]) for b in ok_names]
            sim_matrix.append(row)
        basis = "jaccard"

    # Consensus: the mean of the off-diagonal pairs
    consensus = None
    if sim_matrix and len(sim_matrix) > 1:
        off = [
            sim_matrix[i][j]
            for i in range(len(sim_matrix))
            for j in range(len(sim_matrix))
            if i != j
        ]
        consensus = sum(off) / max(1, len(off))

    level = "none"
    if consensus is not None:
        if consensus >= 0.8:
            level = "high"
        elif consensus >= 0.5:
            level = "medium"
        else:
            level = "low"

    if len(ok_names) > 1:
        status = "ok"
    elif ok_names:
        status = "single"
    else:
        status = "empty"

    result = {
        "status": status,
        "asked": asked,
        "models": ok_names,
        "responses": {n: responses[n][:600] for n in ok_names},
        "similarity_matrix": sim_matrix,
        "consensus_score": round(consensus, 3) if consensus is not None else None,
        "consensus_level": level,
        "similarity_basis": basis,
        "note": _note(basis, asked, ok_names),
    }
    _last[tenant_id or "default"] = {
        # The answers themselves are left out: this is a status widget, and
        # somebody else's question does not belong in an operator's dashboard.
        k: v
        for k, v in result.items()
        if k != "responses"
    } | {"last_call_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return result


def _note(basis: str, asked: List[str], answered: List[str]) -> str:
    """One line describing the run that actually happened."""
    if basis == "embedding":
        return "Agreement measured with Cohere embeddings."
    if basis == "jaccard":
        return (
            "Agreement measured by word overlap — no Cohere embedding available, "
            "so treat the percentage as rough."
        )
    if len(asked) < 2:
        return (
            "Only one provider is configured, so there is nothing to compare "
            "against. Add a second key from a different provider and this "
            "becomes a real second opinion."
        )
    quiet = [a for a in asked if a not in answered]
    return (
        "No comparison was possible: "
        + (f"{', '.join(quiet)} did not answer." if quiet else "nobody answered.")
    )
