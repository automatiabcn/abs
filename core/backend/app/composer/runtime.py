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


_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        ".cache",
        "out",
        "target",
        ".idea",
        ".vscode",
    }
)
_CODE_SUFFIXES = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".rb",
        ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".php",
        ".sh", ".sql", ".css", ".scss", ".html", ".vue", ".svelte", ".md",
        ".json", ".yaml", ".yml", ".toml",
    }
)
_MAX_LISTED_FILES = 200


def workspace_files(root: str, *, limit: int = _MAX_LISTED_FILES) -> List[str]:
    """Workspace-relative paths of the code files a proposal may touch.

    The model was asked for a "workspace-relative path" without ever being told
    which paths exist, so it invented plausible ones (a proposal for
    ``src/utils.js`` in a workspace whose only file is ``util.py``). The engine
    caught it, but a proposal against a file that is not there is wasted work
    and reads as a product that does not know your repository.

    Deterministic, local, no model call. Sorted so the same workspace always
    produces the same prompt (a prompt that shuffles defeats caching and makes
    runs unreproducible).
    """
    out: List[str] = []
    try:
        base = os.path.realpath(root)
    except OSError:
        return out
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in _CODE_SUFFIXES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), base)
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


_MAX_CONTEXT_CHARS = 14000
_MAX_CONTEXT_FILES = 8
_MAX_FILE_CHARS = 6000
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is", "be",
        "make", "change", "add", "remove", "fix", "update", "instead", "please",
        "should", "with", "that", "this", "it", "so", "from", "into", "return",
    }
)


def _task_terms(task: str) -> List[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", task.lower())
    return [w for w in dict.fromkeys(words) if w not in _STOPWORDS]


def relevant_files(root: str, task: str, files: List[str]) -> List[Tuple[str, str]]:
    """The files most likely to be edited, with their current contents.

    Knowing a file's NAME is not knowing its lines. Given only a listing, the
    model wrote a diff against the file it imagined — the path was right, the
    context lines were invented, and the patch could not be applied byte-for-
    byte (measured live: valid=True, dry_run_ok=False).

    Ranking is deterministic and local — no model call, no embedding: a term
    from the task matching the file's name counts for more than one matching
    its body, because that is how developers name things. Ties break on path
    so the same task against the same workspace builds the same prompt.
    """
    terms = _task_terms(task)
    base = os.path.realpath(root)
    scored: List[Tuple[int, str, str]] = []
    for rel in files:
        try:
            with open(os.path.join(base, rel), "r", encoding="utf-8") as fh:
                body = fh.read(_MAX_FILE_CHARS)
        except (OSError, UnicodeDecodeError):
            continue
        low = body.lower()
        name = rel.lower()
        score = 0
        for term in terms:
            if term in name:
                score += 5
            if term in low:
                score += 1
        scored.append((score, rel, body))
    # A small workspace is worth sending whole; in a large one, only what
    # matched the task earns a place in the budget.
    scored.sort(key=lambda t: (-t[0], t[1]))
    out: List[Tuple[str, str]] = []
    spent = 0
    for score, rel, body in scored:
        if out and score == 0 and len(scored) > _MAX_CONTEXT_FILES:
            break
        if spent + len(body) > _MAX_CONTEXT_CHARS or len(out) >= _MAX_CONTEXT_FILES:
            break
        out.append((rel, body))
        spent += len(body)
    return out


def _prompt(
    task: str,
    files: Optional[List[str]] = None,
    contents: Optional[List[Tuple[str, str]]] = None,
) -> str:
    listing = ""
    if files:
        shown = "\n".join(files)
        # Say when the list is cut off: a model told "these are the files" will
        # not look for a file it cannot see, and silently truncating turns a
        # partial list into a false statement about the workspace.
        more = (
            f"\n(this listing stops at {len(files)} files; others may exist)"
            if len(files) >= _MAX_LISTED_FILES
            else ""
        )
        listing = (
            "\nThese are the files in the workspace. Every path you propose MUST "
            "be one of them, copied exactly — do not invent a path, and do not "
            "propose creating a new file:\n" + shown + more + "\n"
        )
    body = ""
    if contents:
        parts = [
            f"\n----- {rel} -----\n{text}" for rel, text in contents
        ]
        body = (
            "\nCurrent contents of the files most likely to change. Your context "
            "and removed lines must match these EXACTLY, character for "
            "character — copy them, do not retype them from memory:\n"
            + "".join(parts)
            + "\n"
        )
    return (
        "You are a senior engineer proposing a precise, minimal multi-file code "
        "change. Reply with exactly one JSON object and nothing else — first "
        "character '{'. Schema:\n"
        '{"summary": "one or two sentences", '
        '"edits": [{"path": "workspace-relative path", '
        '"unified_diff": "a valid unified diff with @@ hunks", '
        '"rationale": "why", "confidence": 0.0-1.0}]}\n'
        "Diff format is strict: EVERY line inside a hunk starts with exactly "
        "ONE marker character — '-', '+' or a single space for context — "
        "immediately followed by the line's real content. Do NOT put a space "
        "after the marker, do not leave any line unmarked, and reproduce the "
        "file's own indentation exactly; a patch whose content does not match "
        "the file byte-for-byte cannot be applied.\n"
        # An instruction describes the format; an example shows it. Live runs
        # kept marking only the first line and leaving the rest bare, or
        # writing "- def f():" with a courtesy space, until the prompt carried
        # a diff to copy the shape from.
        "This is exactly the shape required — for a file containing\n"
        "def helper():\n    return 1\n"
        "a correct edit is:\n"
        "@@ -1,2 +1,2 @@\n"
        " def helper():\n"
        "-    return 1\n"
        "+    return 2\n"
        "Note: the header has no leading space; the context line begins with "
        "one space then 'def'; the changed lines begin with '-' or '+' then "
        "the four spaces of the original indentation.\n"
        "Keep diffs minimal and context-accurate.\n"
        + listing
        + body
        + "\nTASK: "
        + task
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
    files: Optional[List[str]] = None,
    contents: Optional[List[Tuple[str, str]]] = None,
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
            _prompt(task, files, contents),
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
    """Deterministic risk from blast-radius, CORRECTNESS and dry-run validity.

    The gate exists so a dangerous change cannot reach the developer unreviewed.
    House style is not danger. The Senior Judge blends 60% AST fingerprint
    (docstrings, type hints) with 40% model opinion, so gating on the blend
    stopped correct, minimal edits for having no docstring — the exact edits the
    judge is prompted to score highly. Measured: model 8.0, fingerprint 0.0,
    blend 3.2, run gated as high risk.

    So the quality half of the gate reads the CORRECTNESS leg, and style travels
    with the edit as teaching notes instead. When the model leg is missing the
    blend is the only signal there is, and it is used rather than waving the
    edit through.
    """
    risk = "low"
    for e in edits:
        affected = int((e.blast_radius or {}).get("total_affected", 0) or 0)
        quality = e.judge_correctness if e.judge_correctness is not None else e.judge_score
        low_quality = quality is not None and quality < _JUDGE_LOW
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
    # What the workspace actually contains, before asking for a change to it.
    # Reading the tree is local and deterministic; a failure here costs the
    # model its file list, never the run.
    try:
        files = workspace_files(workspace_root)
    except Exception as exc:  # noqa: BLE001
        logger.info("composer workspace listing skipped: %s", exc)
        files = []
    try:
        contents = relevant_files(workspace_root, task, files) if files else []
    except Exception as exc:  # noqa: BLE001
        logger.info("composer context read skipped: %s", exc)
        contents = []

    parsed, tried, gen_meta = await _generate_edits(
        task,
        tenant_id=tenant_id,
        project_slug=project_slug,
        user_subject=user_subject,
        files=files,
        contents=contents,
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
        # One diff from here on: the shape the engine read, which is the shape
        # it would apply. Grading, rendering and applying a different text than
        # the one that lands is how a score ends up describing a change nobody
        # is making.
        diff = patch_engine.normalize_diff(str(raw.get("unified_diff") or ""))
        abs_path = path if os.path.isabs(path) else os.path.join(workspace_root, path)

        v = patch_engine.validate(abs_path, diff, workspace_root=workspace_root)
        dry_ok = False
        if v.valid:
            dr = patch_engine.dry_run(abs_path, diff, workspace_root=workspace_root)
            dry_ok = dr.success

        judge_score: Optional[float] = None
        judge_correctness: Optional[float] = None
        judge_style: Optional[float] = None
        judge_notes: List[str] = []
        try:
            jd = await judge_diff(diff, path)
            judge_score = jd.get("combined_score")
            judge_correctness = jd.get("llm_score")
            judge_style = jd.get("ast_score")
            notes = jd.get("teaching")
            judge_notes = list(notes) if isinstance(notes, list) else []
        except Exception as exc:  # noqa: BLE001 — grading is best-effort
            logger.debug("composer judge skipped for %s: %s", path, exc)

        blast = codegraph.blast_radius(path, key=key) if path else {}

        edits.append(
            ProposedEdit(
                path=path,
                unified_diff=diff,
                rationale=str(raw.get("rationale") or ""),
                judge_score=judge_score,
                judge_correctness=judge_correctness,
                judge_style=judge_style,
                judge_notes=judge_notes,
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
