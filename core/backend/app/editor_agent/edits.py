# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""propose_edit: the one tool that changes a file, and why it never does so
directly.

The model gives a `search` block (copied from what it read) and a `replace`
block. This module turns that into a unified diff the same way Composer
does — difflib over the real file, so the diff cannot fail to apply for a
reason the model invented — then runs the patch engine's validate and
dry-run, grades the diff with the senior judge, and reads the blast radius.
What goes back is a proposal the editor shows as a diff card; the file is
written only when the developer clicks Approve, in the editor, on their
machine (the same path Composer's Approve takes, checkpoint included).

The search/replace shape is the one every agent that edits reliably has
settled on: a whole-file rewrite from a
mid-size model loses lines; a hand-written unified diff has wrong context
lines; an exact block from a file it just read is what a model gets right.
When the block is not found, the model is told so with the closest lines —
a retry with better context is one step, a silent failure is a dead end.
"""

from __future__ import annotations

import difflib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A search block must be unique in the file. Below this many lines a match
# is very often not — the model is asked for more context rather than
# guessing which of the `return x` lines it meant.
MIN_SEARCH_LINES = 1


def _inside(root: str, rel: str) -> Optional[str]:
    from app.chat.context import _inside as inside

    return inside(os.path.realpath(root), rel)


def _find(text: str, search: str) -> Tuple[List[int], str]:
    """Where `search` occurs in `text` (character offsets), and how it was
    matched: 'exact' | 'stripped' (trailing whitespace ignored per line) |
    'dedented' (leading whitespace ignored per line)."""
    if not search:
        return [], "exact"
    idx: List[int] = []
    start = 0
    while True:
        i = text.find(search, start)
        if i < 0:
            break
        idx.append(i)
        start = i + 1
    if idx:
        return idx, "exact"
    # Line-wise tolerant matches: models drop trailing spaces and, more
    # often, get the indentation of the first line wrong.
    t_lines = text.splitlines(keepends=True)
    s_lines = [l.rstrip() for l in search.splitlines()]
    if not s_lines:
        return [], "exact"

    def _scan(norm) -> List[int]:
        found: List[int] = []
        target = [norm(l) for l in s_lines]
        offsets = []
        pos = 0
        for line in t_lines:
            offsets.append(pos)
            pos += len(line)
        for i in range(0, len(t_lines) - len(target) + 1):
            window = [norm(t_lines[i + k].rstrip("\r\n")) for k in range(len(target))]
            if window == target:
                found.append(i)
        return found

    hits = _scan(lambda l: l.rstrip())
    how = "stripped"
    if not hits:
        hits = _scan(lambda l: l.strip())
        how = "dedented"
    if not hits:
        return [], "exact"
    # Convert line hits to character offsets of the whole block.
    offsets = []
    pos = 0
    for line in t_lines:
        offsets.append(pos)
        pos += len(line)
    return [offsets[h] for h in hits], how


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _reindent(block: str, search: str, replace: str) -> str:
    """Give `replace` the file's indentation when `search` matched only
    after stripping. Each search line that is still present in `replace`
    carries its file indentation over; a new line takes the indentation
    delta of the last carried line, so an inserted `if` under a dedented
    `def` lands where the file's `def` body is."""
    file_lines = block.splitlines()
    s_lines = search.splitlines()
    pos_deltas = [len(_indent_of(f)) - len(_indent_of(sl)) for f, sl in zip(file_lines, s_lines)]
    by_content: dict = {}
    for sl, d in zip(s_lines, pos_deltas):
        by_content.setdefault(sl.strip(), []).append(d)
    delta = pos_deltas[0] if pos_deltas else 0
    out = []
    for j, rl in enumerate(replace.splitlines()):
        key = rl.strip()
        if key in by_content and by_content[key]:
            delta = by_content[key].pop(0)  # an unchanged line: its own place
        elif j < len(pos_deltas):
            delta = pos_deltas[j]  # a changed line: the line it replaces
        width = max(0, len(_indent_of(rl)) + delta)
        out.append((" " * width + rl.lstrip()) if key else "")
    return "\n".join(out)


def _replace_block(text: str, search: str, replace: str, at: int, how: str) -> str:
    """Splice `replace` over the block that starts at `at`. For tolerant
    matches the block spans the same number of lines as `search`."""
    n_lines = len(search.splitlines())
    if how == "exact":
        return text[:at] + replace + text[at + len(search) :]
    end = at
    for _ in range(n_lines):
        nl = text.find("\n", end)
        end = len(text) if nl < 0 else nl + 1
    block = text[at:end]
    new = _reindent(block, search, replace) if how == "dedented" else replace
    if block.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    return text[:at] + new + text[end:]


def _closest(text: str, search: str, n: int = 6) -> List[str]:
    """Lines of the file that resemble the first line of the search block —
    what the model needs to try again."""
    first = (search.splitlines() or [""])[0].strip()
    if not first:
        return []
    lines = text.splitlines()
    scored = []
    for i, line in enumerate(lines):
        r = difflib.SequenceMatcher(None, first, line.strip()).ratio()
        if r > 0.5:
            scored.append((r, i, line))
    scored.sort(key=lambda t: -t[0])
    return [f"{i + 1}: {line}" for _score, i, line in scored[:n]]


def _diff(rel: str, old: str, new: str) -> str:
    if old.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    if new == old:
        return ""
    d = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        n=3,
    )
    text = "".join(d)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _stats(diff: str) -> Tuple[int, int]:
    plus = minus = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            plus += 1
        elif line.startswith("-") and not line.startswith("---"):
            minus += 1
    return plus, minus


async def propose_edit(
    *,
    root: str,
    path: str,
    search: str = "",
    replace: str = "",
    new_content: Optional[str] = None,
    rationale: str = "",
    tenant: Optional[str] = None,
    user: Optional[str] = None,
) -> Dict[str, Any]:
    """Build, check and grade one edit. Never writes.

    Returns {ok, path, unified_diff, added, removed, judge_score, judge_notes,
    blast_radius, validation, dry_run_ok, rationale, model_note} — or
    {ok: False, error, model_note}. `model_note` is the sentence that goes
    back into the transcript for the model.
    """
    from app.chat.cleanup import normalise_rel

    rel = normalise_rel(path)
    full = _inside(root, rel) if rel else None
    if not full:
        return {
            "ok": False,
            "error": "outside_project",
            "model_note": f"propose_edit refused: '{path}' is not a path inside the project.",
        }
    if not os.path.isfile(full):
        return {
            "ok": False,
            "error": "not_found",
            "model_note": (
                f"propose_edit failed: {rel} does not exist. Use create_file for a new "
                "file, or list_dir to find the right path."
            ),
        }
    try:
        with open(full, "r", encoding="utf-8") as fh:
            old = fh.read()
    except (OSError, UnicodeDecodeError):
        return {
            "ok": False,
            "error": "unreadable",
            "model_note": f"propose_edit failed: {rel} is not readable as text.",
        }

    if isinstance(new_content, str) and new_content.strip():
        from app.composer.from_content import _looks_truncated

        old_n, new_n = old.count("\n"), new_content.count("\n")
        if _looks_truncated(old, new_content) or (old_n >= 8 and new_n < old_n * 0.4):
            return {
                "ok": False,
                "error": "looks_truncated",
                "model_note": (
                    f"propose_edit refused: your new_content for {rel} is much shorter than "
                    f"the file ({old.count(chr(10))} lines → {new_content.count(chr(10))}). "
                    "Use search/replace for the part you want to change."
                ),
            }
        new = new_content
        how = "whole"
    else:
        if not search:
            return {
                "ok": False,
                "error": "no_search",
                "model_note": "propose_edit failed: give `search` and `replace`, or `new_content`.",
            }
        hits, how = _find(old, search)
        if not hits:
            near = _closest(old, search)
            hint = ("\nClosest lines in the file:\n" + "\n".join(near)) if near else ""
            return {
                "ok": False,
                "error": "search_not_found",
                "model_note": (
                    f"propose_edit failed: the `search` text was not found in {rel}. Copy it "
                    f"exactly from a read_file result (indentation included).{hint}"
                ),
            }
        if len(hits) > 1:
            return {
                "ok": False,
                "error": "ambiguous",
                "model_note": (
                    f"propose_edit failed: the `search` text occurs {len(hits)} times in {rel}. "
                    "Include more surrounding lines so it is unique."
                ),
            }
        new = _replace_block(old, search, replace or "", hits[0], how)

    diff = _diff(rel, old, new)
    if not diff:
        return {
            "ok": False,
            "error": "no_change",
            "model_note": f"propose_edit: the edit leaves {rel} unchanged; nothing to apply.",
        }

    from app.patches import engine as patch_engine

    v = patch_engine.validate(full, diff, workspace_root=root)
    dry_ok = False
    if v.valid:
        dr = patch_engine.dry_run(full, diff, workspace_root=root)
        dry_ok = bool(dr.success)
        if dr.success and getattr(dr, "repaired_diff", ""):
            diff = dr.repaired_diff
    validation = {"valid": v.valid, "stage": v.stage, "reason": v.reason}
    if not v.valid or not dry_ok:
        why = v.reason if not v.valid else "dry run failed"
        return {
            "ok": False,
            "error": "will_not_apply",
            "validation": validation,
            "unified_diff": diff,
            "model_note": f"propose_edit failed: the change to {rel} cannot be applied ({why}).",
        }

    judge_score: Optional[float] = None
    judge_notes: List[str] = []
    try:
        from app.judge.senior import judge_diff

        jd = await judge_diff(diff, rel, tenant_id=tenant, user_subject=user)
        judge_score = jd.get("combined_score")
        notes = jd.get("teaching")
        judge_notes = list(notes) if isinstance(notes, list) else ([str(notes)] if notes else [])
    except Exception as exc:  # noqa: BLE001 — grading is best-effort
        logger.debug("propose_edit judge skipped for %s: %s", rel, exc)

    blast: Dict[str, Any] = {}
    try:
        from app.codegraph import graph as codegraph
        from app.codegraph.graph import tenant_key as _key_for

        blast = codegraph.blast_radius(rel, key=_key_for(tenant or "_global", root)) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("propose_edit blast skipped for %s: %s", rel, exc)

    plus, minus = _stats(diff)
    grade = f", judge {judge_score:.1f}/10" if isinstance(judge_score, (int, float)) else ""
    return {
        "ok": True,
        "path": rel,
        "unified_diff": diff,
        "added": plus,
        "removed": minus,
        "match": how,
        "judge_score": judge_score,
        "judge_notes": judge_notes[:4],
        "blast_radius": blast,
        "validation": validation,
        "dry_run_ok": True,
        "rationale": rationale or "",
        "model_note": (
            f"Edit prepared for {rel} (+{plus}/-{minus}{grade}). It is shown to the "
            "developer as a diff; the next result says whether it was applied."
        ),
    }
