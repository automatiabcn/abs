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
from app.composer import from_content
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

# Room for the answer. The prompt asks for `new_content` — the COMPLETE file —
# and the ceiling was still the one the old diff-sized answers had left behind:
# 1500. A 200-line source file is already past that, so the reply arrived cut
# off mid-JSON, `_parse` found no balanced object, and the run came back with
# zero edits and an empty summary while the call had been made and billed
# (measured 08-02: eight tasks, eight providers answered, eight empty
# proposals). If the prompt ever goes back to asking for a diff, this comes
# down with it — the two have to move together.
_MAX_OUTPUT_TOKENS = 8000


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
    # What must not become model context: .gitignore/.absignore'd paths and
    # credential-shaped files. This walk used to know only suffixes, and a
    # secrets.yaml the developer had told git to forget went to a cloud model
    # as "project context" (audit, 2026-08-18). One rule set, shared with RAG.
    from app.context.exclusions import IgnoreMatcher, excluded_reason

    ignore = IgnoreMatcher(base)
    for dirpath, dirnames, filenames in os.walk(base):
        kept_dirs = []
        for d in sorted(dirnames):
            if d in _SKIP_DIRS or d.startswith("."):
                continue
            rel_d = os.path.relpath(os.path.join(dirpath, d), base)
            try:
                if ignore.is_ignored(rel_d, is_dir=True):
                    continue
            except Exception:  # noqa: BLE001 — a broken ignore file widens nothing
                pass
            kept_dirs.append(d)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in _CODE_SUFFIXES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), base)
            if excluded_reason(rel, ignore) is not None:
                continue
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


def _graph_neighbours(root: str, seeds: List[str], key: str) -> set[str]:
    """Workspace-relative files that break if any of `seeds` changes.

    `seeds` are the words of the task and the best lexical file matches. Asking
    by SYMBOL is the important half: when somebody writes "change
    apply_discount", term matching can only find files containing that string —
    the definition, the callers, and every comment that mentions it, all tied
    at one point each. The graph is the only thing here that knows which of
    them would actually break, and it was already computing that list for the
    blast-radius badge while the prompt went out without it.

    `blast_radius` answers in absolute paths and the ranking works in relative
    ones; a comparison across the two never matches, quietly, which is what the
    first version of this did.
    """
    base = os.path.realpath(root)
    out: set[str] = set()
    for seed in seeds:
        try:
            blast = codegraph.blast_radius(seed, key=key) or {}
        except Exception as exc:  # noqa: BLE001 — context is an aid, not a gate
            logger.info("composer graph expansion skipped for %s: %s", seed, exc)
            continue
        if not blast.get("found"):
            continue
        for path in blast.get("affected_files") or []:
            if not path:
                continue
            real = os.path.realpath(str(path))
            rel = os.path.relpath(real, base)
            if not rel.startswith(".."):
                out.add(rel)
    return out


# How many top-scoring files also get used as graph seeds, and what a graph hit
# is worth. Below a name match (5) on purpose: a file the task names by hand is
# a better guess than one inferred from an edge.
_GRAPH_SEEDS = 3
_GRAPH_SCORE = 3


def relevant_files(
    root: str,
    task: str,
    files: List[str],
    *,
    graph_key: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """The files most likely to be edited, with their current contents.

    Knowing a file's NAME is not knowing its lines. Given only a listing, the
    model wrote a diff against the file it imagined — the path was right, the
    context lines were invented, and the patch could not be applied byte-for-
    byte (measured live: valid=True, dry_run_ok=False).

    Ranking is deterministic and local — no model call, no embedding: a term
    from the task matching the file's name counts for more than one matching
    its body, because that is how developers name things. Ties break on path
    so the same task against the same workspace builds the same prompt.

    With `graph_key`, the top lexical matches are then expanded with the files
    that depend on them. Neighbours compete for the same slots rather than
    adding new ones — a context window does not grow because a feature was
    added, and on a monorepo that difference is the whole game.
    """
    terms = _task_terms(task)
    base = os.path.realpath(root)
    scored: List[Tuple[int, str, str]] = []
    # Callers may hand in a listing they built themselves; the exclusions
    # apply here too, or a caller that skipped workspace_files() would leak.
    from app.context.exclusions import IgnoreMatcher, excluded_reason, redact_secrets

    ignore = IgnoreMatcher(base)
    for rel in files:
        if excluded_reason(rel, ignore) is not None:
            continue
        try:
            with open(os.path.join(base, rel), "r", encoding="utf-8") as fh:
                body = fh.read(_MAX_FILE_CHARS)
        except (OSError, UnicodeDecodeError):
            continue
        # A token in line 12 of an otherwise useful file leaves as a marker.
        body, _redacted = redact_secrets(body)
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

    if graph_key:
        # Symbols named in the task first — that is the query the graph is for.
        # The best lexical files follow, for tasks phrased without a symbol
        # ("make invoicing handle percentages").
        seeds = terms + [rel for score, rel, _b in scored[:_GRAPH_SEEDS] if score > 0]
        if seeds:
            related = _graph_neighbours(base, seeds, graph_key)
            if related:
                scored = [
                    (s + _GRAPH_SCORE if rel in related else s, rel, b)
                    for s, rel, b in scored
                ]
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
        '"new_content": "the COMPLETE file exactly as it should be afterwards", '
        '"rationale": "why", "confidence": 0.0-1.0}]}\n'
        # We used to ask for a unified diff here, with a strict format spec and
        # a worked example. Measured 08-02 on the free tiers: three proposals
        # in a row were unapplicable — invented context lines, indentation off
        # by four spaces, hunk counts that did not match their bodies. The
        # prompt was not the problem; a unified diff is a machine format with
        # byte-exact obligations, and that is the wrong thing to ask a model
        # for. It returns the finished file; ABS computes the diff from the
        # bytes on disk, so the result applies by construction.
        "Return the WHOLE file in new_content, from its first line to its "
        "last, with your change made — not a fragment, not a diff, not an "
        "ellipsis. Copy every line you are not changing exactly as it is, "
        "including blank lines and indentation. Change as little as the task "
        "requires.\n"
        "For a file containing\n"
        "def helper():\n    return 1\n"
        "asked to return 2, new_content is exactly:\n"
        "def helper():\n    return 2\n"
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
        # A paid provider runs on the key of the person asking. The server's
        # own paid key is the operator's; a member's Composer does not spend it
        # unless the operator shared it (app/providers/paid_access).
        from app.providers.paid_access import restrict_chain

        active = restrict_chain(active, extra, user_subject)
        # A multi-file edit is the hardest thing we ask a model to do, so the
        # order is reconsidered for THIS kind of work rather than inherited
        # from the cost-first default. A preference, never a requirement: with
        # one free key the chain is that key, and the proposal still runs.
        from app.cascade.routing import DEEP, chain_for

        active = chain_for(DEEP, active) or active
        if not active:
            return {}, [], {}
        primary, *rest = active

        async def _ask(structured: bool):
            return await call_with_cascade(
                _prompt(task, files, contents),
                primary=primary,
                fallbacks=tuple(rest),
                # Named per provider, not left to the adapter and not one name
                # forced on the whole chain — see `_COMPOSER_MODELS`.
                models=_COMPOSER_MODELS,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=0.1,
                **({"response_format": {"type": "json_object"}} if structured else {}),
                tenant_id=tenant_id,
                project_slug=project_slug,
                user_subject=user_subject,
            )

        try:
            resp = await _ask(True)
        except Exception as exc:  # noqa: BLE001
            if not _is_json_mode_refusal(exc):
                raise
            # The provider's validator rejected the answer, not the request.
            # That is a 400 — permanent — so the cascade gives up, and on a
            # free-tier install with one provider there is nowhere to give up
            # to: the developer got an empty proposal and no reason (found by
            # the effectiveness harness on its first real task, 08-02).
            #
            # Strictness was never the point. `_parse` already strips fences
            # and pulls the first balanced object out of prose, because models
            # wrap JSON in explanation. So the same prompt goes once more
            # without the flag it failed on, and the answer is read the
            # defensive way.
            logger.info("composer retrying without JSON mode: %s", str(exc)[:120])
            resp = await _ask(False)
        meta: dict = {
            "provider": getattr(resp, "provider", "") or "",
            # The provider's own word on whether it finished. Until 08-05 this
            # was inferred from a log line further down that says "likely
            # truncated" — a guess made in the one place that could have
            # simply asked.
            "truncated": bool(getattr(resp, "truncated", False)),
        }
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
        text = getattr(resp, "text", "") or ""
        parsed = _parse(text)
        if text.strip() and not parsed:
            # The answer arrived and could not be read — truncation, usually.
            # Reporting that the same way as "no answer" tells the reader the
            # model had nothing to suggest, which is not what happened.
            meta["parse_failed"] = True
            logger.info(
                "composer answer unparseable (%d chars from %s) — likely truncated",
                len(text), meta.get("provider") or "?",
            )
        return (
            parsed,
            list(getattr(resp, "providers_tried", []) or []),
            meta,
        )
    except Exception as exc:  # noqa: BLE001 — degrade, never 500
        logger.info("composer generation degraded: %s", exc)
        return {}, [], {}


# A capable model per provider, by name. Without this every adapter falls back
# to its own `default_model`, and Groq's is an 8B instant model that leads the
# default free-first chain — so the product's flagship feature was running on
# the weakest model the account owns, against a prompt carrying up to 14k
# characters of workspace. It answered 413 (found by the effectiveness harness,
# 08-02). The judge pins models for comparability; the Composer pins them
# because a multi-file edit is the hardest thing we ask a model to do.
#
# A provider missing from this map keeps its own default on purpose: inventing
# a model name is how a perfectly good key starts returning 404.
_COMPOSER_MODELS: dict[str, str] = {
    "groq": "openai/gpt-oss-120b",
    "cerebras": "gpt-oss-120b",
}


def model_for(provider: str) -> Optional[str]:
    """The model to ask this provider for, or None to accept its default."""
    return _COMPOSER_MODELS.get(str(provider or "").strip().lower())


def _is_json_mode_refusal(exc: BaseException) -> bool:
    """Did the provider reject the ANSWER's shape rather than the request?

    Narrow on purpose. A quota error, a bad key or a timeout mean something
    else entirely, and retrying those would double every real outage — and
    spend twice the allowance of a provider that just said it has none left.
    """
    text = str(exc).lower()
    return "json_validate_failed" in text or (
        "failed to generate json" in text and "400" in text
    )


def _clamp01(value: Any) -> Optional[float]:
    """The model's self-reported confidence, or None when it did not say.

    This returned 0.0 for a missing field, and the panel draws "uncertain" below
    0.5 — so every edit where the model simply omitted the number was shown as
    an edit the model doubted. A warning that fires on the ordinary case is a
    warning nobody reads by the time it matters.
    """
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


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
    key = graph_key or codegraph.workspace_key(workspace_root)

    # Index BEFORE the model is asked, not after. The graph used to be built
    # only in time to draw the blast-radius badge, which meant the badge could
    # name three files the prompt had never shown — the product knew which
    # files an edit would break and did not tell the model. Deterministic,
    # local, no model call; a failure costs context, never the run.
    try:
        codegraph.build(workspace_root, key=key)
        graph_ready = True
    except Exception as exc:  # noqa: BLE001
        logger.info("composer codegraph build skipped: %s", exc)
        graph_ready = False

    try:
        contents = (
            relevant_files(
                workspace_root, task, files, graph_key=key if graph_ready else None
            )
            if files
            else []
        )
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

    # The graph was built above, before the prompt went out, so the blast-radius
    # badge and the context the model saw are drawn from the same index. One
    # retry here for the case where the earlier build failed but the query path
    # might still work — without it a workspace nobody ran code_graph_build on
    # loses the badge that makes a proposal worth trusting.
    if raw_edits and not graph_ready:
        try:
            codegraph.build(workspace_root, key=key)
        except Exception as exc:  # noqa: BLE001 — blast-radius is an annotation
            logger.info("composer codegraph rebuild skipped: %s", exc)

    edits: List[ProposedEdit] = []
    refused: List[str] = []
    # If the generation stopped at the token limit, every edit it produced is
    # suspect — including the ones that look whole. The last file in a
    # truncated answer is the one that was being written when the room ran
    # out, and there is no way to tell from here which one that was.
    generation_cut_off = bool(gen_meta.get("truncated"))
    for raw in raw_edits:
        if not isinstance(raw, dict):
            continue
        if generation_cut_off:
            raw = {**raw, "truncated": True}
        path = str(raw.get("path") or "").strip()
        # One diff from here on: the shape the engine read, which is the shape
        # it would apply. Grading, rendering and applying a different text than
        # the one that lands is how a score ends up describing a change nobody
        # is making.
        abs_path = path if os.path.isabs(path) else os.path.join(workspace_root, path)
        rel_path = from_content.relative_to(workspace_root, path)

        # Inside the workspace, or not proposed — decided BEFORE anything is
        # read. edit_diff reads the file to build the diff, and a model that
        # named `/etc/passwd` or `../../.env` had that file's lines returned to
        # the caller as the `-` side of a diff before the patch engine ever
        # got to say no (audit, 2026-08-18).
        from app.workspace.roots import within

        if not within(abs_path, workspace_root):
            refused.append(
                f"{rel_path}: outside the open project — not read, not proposed."
            )
            continue

        # Asked before the diff is built, not after.
        #
        # The ratio guards live inside edit_diff and show up as an empty diff,
        # so the refusal below could be read off that. Evidence cannot: a reply
        # the provider called cut off still produces a perfectly well-formed
        # diff, and checking after the fact would never fire on it.
        if generation_cut_off:
            why = from_content.refusal(raw, rel_path=rel_path, abs_path=abs_path)
            if why:
                refused.append(why)
                continue

        # Prefer a diff we computed from the file on disk over one the model
        # wrote. See app/composer/from_content.py for why.
        raw_diff, built_here = from_content.edit_diff(
            raw,
            rel_path=from_content.relative_to(workspace_root, path),
            abs_path=abs_path,
        )
        diff = patch_engine.normalize_diff(raw_diff)
        if not diff:
            # An empty diff has two very different causes and the customer is
            # owed the difference: the model said the file is already right, or
            # we threw its answer away for looking truncated. Only the second
            # gets reported — a note on the ordinary case is a note nobody
            # reads by the time a real one arrives.
            why = from_content.refusal(
                raw,
                rel_path=from_content.relative_to(workspace_root, path),
                abs_path=abs_path,
            )
            if why:
                refused.append(why)
                continue
        if built_here and not diff:
            # The model returned the file unchanged: nothing to propose.
            continue

        v = patch_engine.validate(abs_path, diff, workspace_root=workspace_root)
        dry_ok = False
        if v.valid:
            dr = patch_engine.dry_run(abs_path, diff, workspace_root=workspace_root)
            dry_ok = dr.success
            # The engine may have repaired a model artifact to place the hunks
            # (pure-context "diffs", phantom blank lines). What it actually
            # applied IS the proposal — grade, render and hand the editor that
            # text, or the judge scores a no-op and Approve applies a diff the
            # editor's own strict applier cannot read.
            if dr.success and dr.repaired_diff:
                diff = dr.repaired_diff

        judge_score: Optional[float] = None
        judge_correctness: Optional[float] = None
        judge_style: Optional[float] = None
        judge_notes: List[str] = []
        try:
            jd = await judge_diff(
                diff, path, tenant_id=tenant_id, user_subject=user_subject
            )
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
    summary = str(parsed.get("summary") or "")
    if refused and not edits:
        # The model's paragraph describes the edits we just threw away.
        # "Rewrote the parser and dropped the dead branch" above an empty list
        # reads as a product that lost the work, not one that refused it.
        summary = (
            "Nothing proposed. "
            + " ".join(refused)
            + " The model's own summary is not shown, because it describes "
            "changes that are not in this response."
        )
    elif refused:
        summary = (summary + " " if summary else "") + " ".join(refused)
    return ComposerRun(
        run_id="cmp-" + uuid.uuid4().hex[:12],
        task=task,
        edits=edits,
        summary=summary,
        risk=risk,
        requires_approval=requires_approval,
        providers_tried=tried,
        provider=str(gen_meta.get("provider") or ""),
        cost_usd=gen_meta.get("cost_usd"),
        degraded=not raw_edits,
        refused=refused,
        tenant_slug=tenant_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
