# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agent Runtime — execute one agent against a task.

Flow (design doc §8.1): gather context (RAG citations + graph entities) → build
a scoped system prompt from the agent's allow-list → call the Model Gateway
(tenant-scoped cascade, BYOK-aware) → parse a STRUCTURED result (never free
text) → if the agent's risk needs approval, attach the proposed action for the
Approval Center.

The model call is isolated in ``_complete`` so it degrades gracefully (returns
a low-confidence result instead of a 500) when no provider is configured, and
so tests can stub it without live providers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.registry import Agent, get_agent

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    kind: str  # rag | graph | signal
    ref: str  # source / node / signal id
    excerpt: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "ref": self.ref, "excerpt": self.excerpt}


@dataclass
class AgentResult:
    agent_id: str
    output_kind: str
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    recommended_action: str = ""
    risk: str = "low"
    requires_approval: bool = False
    provider: str = ""
    elapsed_ms: int = 0
    degraded: bool = False  # no provider / unparseable model output

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


def _system_prompt(agent: Agent, task: str, evidence: List[Evidence]) -> str:
    """Scoped instruction: the agent stays inside its purpose + allow-list and
    must answer with STRUCTURED JSON citing the evidence it was given."""
    ev_block = ""
    if evidence:
        lines = [
            f"[{i + 1}] ({e.kind}:{e.ref}) {e.excerpt}".strip()
            for i, e in enumerate(evidence)
        ]
        ev_block = "\nEVIDENCE:\n" + "\n".join(lines)
    tools = ", ".join(agent.tools) or "(none)"
    return (
        f"You are '{agent.name}', an agent whose job is: {agent.purpose}. "
        f"You may use only these tools and data sources: {tools}. "
        "Stay inside that scope. Do not make a recommendation you cannot trace "
        "to the evidence below, and say so plainly when the evidence is thin. "
        "Answer in English.\n"
        "IMPORTANT: reply with exactly one valid JSON object and nothing else. "
        "No markdown, no code fence, no commentary — the first character must "
        "be '{'.\n"
        'Schema: {"summary": "one or two sentences", '
        '"recommended_action": "what to do next", '
        '"confidence": a number from 0.0 to 1.0, '
        '"payload": {...fields for this kind of result...}, '
        '"cited": [indices of the evidence you used]}.'
        f"{ev_block}\n\nTASK: {task}"
    )


async def _gather_evidence(
    agent: Agent, task: str, *, tenant_id: str, project_slug: Optional[str]
) -> List[Evidence]:
    """Best-effort RAG (+ later graph) context. Never raises."""
    ev: List[Evidence] = []
    if any(t in agent.tools for t in ("rag", "cite")) or "rag" in agent.data_sources:
        try:
            from app.chat.citations import retrieve_citations

            cits = await retrieve_citations(task, project=tenant_id, top_k=5)
            for c in cits or []:
                ev.append(
                    Evidence(
                        kind="rag",
                        ref=getattr(c, "source", "") or "",
                        excerpt=(getattr(c, "excerpt", "") or "")[:240],
                    )
                )
        except Exception as exc:  # pragma: no cover — context is best-effort
            logger.debug("agent %s rag context skipped: %s", agent.id, exc)
    return ev


async def _complete(
    agent: Agent,
    prompt: str,
    *,
    tenant_id: str,
    project_slug: Optional[str],
    user_subject: Optional[str],
) -> tuple[str, str]:
    """Call the Model Gateway. Returns (text, provider). Degrades to ("","")
    when no provider is usable so the runtime still returns a structured
    result. Isolated for testability."""
    try:
        from app.cascade.orchestrator import call_with_cascade
        from app.providers.cascade import get_active_providers

        # The caller's own keys count here too. An agent run that ignored them
        # would answer from the free tier while the person's paid key sat unused
        # two rooms away — the same BYOK promise the chat path already keeps.
        extra: frozenset[str] = frozenset()
        try:
            from app.multitenant.provider_keys import tenant_configured_providers

            extra = frozenset(
                tenant_configured_providers(
                    tenant_slug=tenant_id,
                    project_slug=project_slug,
                    user_subject=user_subject,
                )
            )
        except Exception as exc:  # noqa: BLE001 — BYOK is a bonus, never a blocker
            logger.debug("agent BYOK lookup skipped: %s", exc)

        active = get_active_providers(
            prefer=agent.provider_hint, extra_configured=extra
        )
        if not active:
            return "", ""
        primary, *rest = active
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            fallbacks=tuple(rest),
            max_tokens=900,
            # low temperature → more deterministic, more reliably-valid JSON
            temperature=0.1,
            # Groq honours json_object mode → reliably valid JSON; providers that
            # don't support it ignore the kwarg (the robust parse + retry cover
            # the fallback path). Handoff SP-4.
            response_format={"type": "json_object"},
            tenant_id=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
        )
        # ProviderResponse exposes the model text as `.text` (NOT `.completion`)
        # — reading the wrong field made every agent degrade silently.
        return (
            getattr(resp, "text", "") or "",
            getattr(resp, "provider", "") or primary,
        )
    except Exception as exc:  # noqa: BLE001 — degrade, never 500 the runtime
        logger.info("agent %s completion degraded: %s", agent.id, exc)
        return "", ""


def _parse(text: str) -> dict:
    """Defensive JSON extraction. Models often wrap JSON in prose or ```json
    fences; we strip fences, try a direct parse, then extract the FIRST
    balanced ``{...}`` object. Returns {} on failure (caller → degraded)."""
    if not text:
        return {}
    t = text.strip()
    # strip markdown code fences (```json ... ``` / ``` ... ```)
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else {}
    except Exception:
        pass
    # first balanced {...} (handles leading/trailing prose + nested braces)
    start = t.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(t)):
            c = t[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out = json.loads(t[start : i + 1])
                        return out if isinstance(out, dict) else {}
                    except Exception:
                        break
    return {}


async def run_agent(
    agent_id: str,
    task: str,
    *,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> AgentResult:
    """Execute an agent and return a structured result. Raises KeyError for an
    unknown agent; otherwise always returns a result (degraded if the model is
    unavailable)."""
    agent = get_agent(agent_id)
    if agent is None:
        raise KeyError(f"unknown agent: {agent_id}")

    t0 = time.perf_counter()
    evidence = await _gather_evidence(
        agent, task, tenant_id=tenant_id, project_slug=project_slug
    )
    prompt = _system_prompt(agent, task, evidence)
    text, provider = await _complete(
        agent,
        prompt,
        tenant_id=tenant_id,
        project_slug=project_slug,
        user_subject=user_subject,
    )
    parsed = _parse(text)
    # The model occasionally answers in prose instead of JSON. It's stochastic,
    # so a couple of stricter retries recover most of those (degrade ~p^3)
    # without a provider-layer change. Only retry when the model DID respond but
    # unparseably. Root fix = provider JSON-mode (handoff SP-4).
    # One retry only: more retries multiply provider calls and, with a single
    # configured provider, amplify rate-limit (429) degradation. The clean fix
    # that removes the need for retries is provider JSON-mode (handoff SP-4).
    retries = 0
    while not parsed and text and retries < 1:
        retries += 1
        retry_prompt = (
            prompt + "\n\nYour last reply was not valid JSON. Return exactly one "
            "JSON object: first character '{', last character '}'. No markdown, "
            "no explanation, no prose."
        )
        text, provider = await _complete(
            agent,
            retry_prompt,
            tenant_id=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
        )
        parsed = _parse(text)

    summary = str(parsed.get("summary") or "").strip()
    if not summary:
        summary = (
            f"{agent.name}: no usable answer — either no provider replied, or "
            "the reply was not the structured result this agent needs."
            if not text
            else text[:240]
        )
    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # Degraded = the model produced nothing usable (no provider configured, or
    # output that wouldn't parse). A degraded run must NOT be treated as a real
    # proposal: callers skip approval creation, so the Approval Center never
    # fills up with rows that say only "no usable answer".
    degraded = not bool(text) or not bool(parsed)
    return AgentResult(
        agent_id=agent.id,
        output_kind=agent.output_kind,
        summary=summary,
        payload=parsed.get("payload")
        if isinstance(parsed.get("payload"), dict)
        else {},
        evidence=evidence,
        confidence=confidence,
        recommended_action=str(parsed.get("recommended_action") or "").strip(),
        risk=agent.risk,
        # a degraded result is not actionable → no approval gate
        requires_approval=agent.requires_approval and not degraded,
        provider=provider,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        degraded=degraded,
    )
