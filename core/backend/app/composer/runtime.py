# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer runtime — generate multi-file edits, then grade / blast / validate.

Pipeline: ask the cascade (BYOK, JSON mode) for a set of unified-diff edits, then
for each edit run — deterministically, locally — patch_engine.validate + dry_run,
Senior-Judge scoring, and code_graph blast-radius. Risk and the approval gate are
*derived* from those signals, never from the model's word. Nothing is applied
here: the editor reviews the graded diffs and applies via patch_engine.

``_generate_edits`` isolates the model call so it degrades gracefully (no
provider → a degraded run, not a 500) and tests can stub it without live
providers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from app.codegraph import graph as codegraph
from app.composer.schemas import ComposerRun, ProposedEdit
from app.judge.senior import judge_diff
from app.patches import engine as patch_engine

logger = logging.getLogger(__name__)

# Risk thresholds (deterministic, so the editor can trust the gate).
_BLAST_HIGH = 8
_BLAST_MEDIUM = 3
_JUDGE_LOW = 5.0


def _prompt(task: str) -> str:
    return (
        "You are a senior engineer proposing a precise, minimal multi-file code "
        "change. Reply with exactly one JSON object and nothing else — first "
        "character '{'. Schema:\n"
        '{"summary": "one or two sentences", '
        '"edits": [{"path": "workspace-relative path", '
        '"unified_diff": "a valid unified diff with @@ hunks", '
        '"rationale": "why", "confidence": 0.0-1.0}]}\n'
        "Diff format is strict: each line starts with exactly ONE marker "
        "character — '-', '+' or a single space for context — immediately "
        "followed by the line's real content. Do NOT put a space after the "
        "marker, and reproduce the file's own indentation exactly; a patch "
        "whose content does not match the file byte-for-byte cannot be "
        "applied.\n"
        "Keep diffs minimal and context-accurate.\n\nTASK: " + task
    )


def _parse(text: str) -> dict:
    """Defensive JSON extraction (strip fences, first balanced object)."""
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else {}
    except Exception:
        pass
    start = t.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out = json.loads(t[start : i + 1])
                        return out if isinstance(out, dict) else {}
                    except Exception:
                        break
    return {}


async def _generate_edits(
    task: str,
    *,
    tenant_id: str,
    project_slug: Optional[str],
    user_subject: Optional[str],
) -> Tuple[dict, List[str], dict]:
    """Ask the cascade for {summary, edits[]}.

    Returns (parsed, providers_tried, meta) where meta carries the Cost-HUD
    signals: ``{"provider": winner, "cost_usd": float|None}``. Degrades to
    ({}, [], {}) when no provider is usable. Isolated for testability.
    """
    try:
        from app.cascade.orchestrator import call_with_cascade
        from app.providers.cascade import get_active_providers

        extra: frozenset = frozenset()
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
            logger.debug("composer BYOK lookup skipped: %s", exc)

        active = get_active_providers(extra_configured=extra)
        if not active:
            return {}, [], {}
        primary, *rest = active
        resp = await call_with_cascade(
            _prompt(task),
            primary=primary,
            fallbacks=tuple(rest),
            max_tokens=1500,
            temperature=0.1,
            response_format={"type": "json_object"},
            tenant_id=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
        )
        meta: dict = {"provider": getattr(resp, "provider", "") or ""}
        try:
            from app.chat.cost import estimate_call_cost_usd

            est = estimate_call_cost_usd(
                provider=meta["provider"] or None,
                tokens_in=int(getattr(resp, "tokens_in", 0) or 0),
                tokens_out=int(getattr(resp, "tokens_out", 0) or 0),
                model=getattr(resp, "model", None),
            )
            meta["cost_usd"] = est.get("usd")
        except Exception as exc:  # noqa: BLE001 — cost estimate is best-effort
            logger.debug("composer cost estimate skipped: %s", exc)
            meta["cost_usd"] = None
        return (
            _parse(getattr(resp, "text", "") or ""),
            list(getattr(resp, "providers_tried", []) or []),
            meta,
        )
    except Exception as exc:  # noqa: BLE001 — degrade, never 500
        logger.info("composer generation degraded: %s", exc)
        return {}, [], {}


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _derive_risk(edits: List[ProposedEdit]) -> Tuple[str, bool]:
    """Deterministic risk from blast-radius, judge score and dry-run validity."""
    risk = "low"
    for e in edits:
        affected = int((e.blast_radius or {}).get("total_affected", 0) or 0)
        low_quality = e.judge_score is not None and e.judge_score < _JUDGE_LOW
        if affected >= _BLAST_HIGH or low_quality or not e.dry_run_ok:
            return "high", True  # a single dangerous edit gates the whole run
        if affected >= _BLAST_MEDIUM:
            risk = "medium"
    return risk, risk == "medium"


async def run_composer(
    task: str,
    *,
    workspace_root: str,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
    graph_key: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> ComposerRun:
    """Produce a graded, blast-annotated multi-file edit proposal.

    Applies nothing. The editor renders each edit (diff + judge chip + "N files
    affected") and applies approved ones via patch_engine.
    """
    parsed, tried, gen_meta = await _generate_edits(
        task,
        tenant_id=tenant_id,
        project_slug=project_slug,
        user_subject=user_subject,
    )
    raw_edits = parsed.get("edits") if isinstance(parsed.get("edits"), list) else []
    key = graph_key or codegraph.workspace_key(workspace_root)

    # Index the workspace before asking what a change would break. The graph is
    # only ever QUERIED here, so without this the blast-radius is empty on any
    # workspace nobody happened to run code_graph_build on — the badge that
    # makes the proposal worth trusting silently disappears. Deterministic,
    # local, no model call; a failure degrades the badge, never the run.
    if raw_edits:
        try:
            codegraph.build(workspace_root, key=key)
        except Exception as exc:  # noqa: BLE001 — blast-radius is an annotation
            logger.info("composer codegraph build skipped: %s", exc)

    edits: List[ProposedEdit] = []
    for raw in raw_edits:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "").strip()
        diff = str(raw.get("unified_diff") or "")
        abs_path = path if os.path.isabs(path) else os.path.join(workspace_root, path)

        v = patch_engine.validate(abs_path, diff, workspace_root=workspace_root)
        dry_ok = False
        if v.valid:
            dr = patch_engine.dry_run(abs_path, diff, workspace_root=workspace_root)
            dry_ok = dr.success

        judge_score: Optional[float] = None
        try:
            jd = await judge_diff(diff, path)
            judge_score = jd.get("combined_score")
        except Exception as exc:  # noqa: BLE001 — grading is best-effort
            logger.debug("composer judge skipped for %s: %s", path, exc)

        blast = codegraph.blast_radius(path, key=key) if path else {}

        edits.append(
            ProposedEdit(
                path=path,
                unified_diff=diff,
                rationale=str(raw.get("rationale") or ""),
                judge_score=judge_score,
                blast_radius=blast,
                confidence=_clamp01(raw.get("confidence")),
                validation={"valid": v.valid, "stage": v.stage, "reason": v.reason},
                dry_run_ok=dry_ok,
            )
        )

    risk, requires_approval = _derive_risk(edits)
    return ComposerRun(
        run_id="cmp-" + uuid.uuid4().hex[:12],
        task=task,
        edits=edits,
        summary=str(parsed.get("summary") or ""),
        risk=risk,
        requires_approval=requires_approval,
        providers_tried=tried,
        provider=str(gen_meta.get("provider") or ""),
        cost_usd=gen_meta.get("cost_usd"),
        degraded=not raw_edits,
        tenant_slug=tenant_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
