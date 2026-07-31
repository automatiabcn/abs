# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Patch engine — Diff-First core: parse, validate, dry-run, apply and score.

An LLM returns a unified diff instead of a whole file. This module turns that
diff into a safe, deterministic edit:

  1. parse_diff():  strict-ish, pure-Python unified-diff reader (lenient on the
                    header line counts so slightly-off diffs still parse).
  2. validate():    multi-stage, fail-fast guard
                    (syntax -> path -> WORKSPACE SANDBOX -> exists -> binary ->
                     size -> policy). The sandbox stage is the multi-tenant
                     safety boundary the old subprocess-`patch` engine lacked.
  3. dry_run():     in-memory apply (falls back to `git apply --check`) — the
                    file is never touched.
  4. apply():       context-verified in-memory apply -> atomic write -> AST
                    re-parse -> automatic rollback from backup on syntax error.
  5. score():       0-10 deterministic quality (minimalism, concentration).

Rich API (used by the Composer):
  parse_diff(text)               -> list[Hunk]
  validate(path, diff, *, ...)   -> ValidationResult
  dry_run(path, diff, *, ...)    -> DryRunResult
  apply(path, diff, *, ...)      -> ApplyResult
  score(diff)                    -> ScoreResult

Back-compat dict API (used by the MCP tools, kept identical):
  preview_patch(path, diff)      -> dict{success, reason, ...}
  apply_patch(path, diff, backup)-> dict{success, reason, backup_path, ...}
  score_patch(diff)              -> dict{score, hunk_count, minimal_ratio,
                                         max_hunk_size, teaching}

Workspace sandbox: pass `workspace_root=` (or set env ABS_WORKSPACE_ROOT). When
set, any target outside the real path of that root is rejected at the `sandbox`
stage — this defeats `..` traversal and symlink escape. When unset, no sandbox
is enforced (the raw preview_patch/apply_patch MCP tools stay gated off by
`settings.mcp_expose_patch_tools`; the Composer always passes a workspace_root).
"""

from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HunkLine:
    """One diff line — op in {' ', '+', '-'}. ' ' is context."""

    op: str
    text: str

    @property
    def is_add(self) -> bool:
        return self.op == "+"

    @property
    def is_del(self) -> bool:
        return self.op == "-"

    @property
    def is_ctx(self) -> bool:
        return self.op == " "


@dataclass
class Hunk:
    """An `@@ -old_start,old_count +new_start,new_count @@` block."""

    old_start: int
    new_start: int
    old_count: int = 1
    new_count: int = 1
    section: str = ""
    lines: List[HunkLine] = field(default_factory=list)

    @property
    def adds(self) -> int:
        return sum(1 for line in self.lines if line.is_add)

    @property
    def dels(self) -> int:
        return sum(1 for line in self.lines if line.is_del)

    @property
    def ctx(self) -> int:
        return sum(1 for line in self.lines if line.is_ctx)


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    stage: str = ""  # which stage rejected it
    meta: dict = field(default_factory=dict)


@dataclass
class DryRunResult:
    success: bool
    method: str  # "inmemory", "git", "validate", "all-failed"
    preview: str = ""  # patched content (truncated)
    reason: str = ""
    # The diff as the engine ACTUALLY applied it — placements resolved and
    # model artifacts repaired. Empty when the run failed or used the git
    # fallback. Downstream (judge, panel, editor applier) should prefer this
    # text: the score on screen must belong to the change being approved.
    repaired_diff: str = ""


@dataclass
class ApplyResult:
    success: bool
    file_path: str
    backup_path: Optional[str] = None
    hunks_applied: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    reason: str = ""
    elapsed: float = 0.0


@dataclass
class ScoreResult:
    score: float  # 0-10
    minimal_ratio: float  # ctx / (ctx+adds+dels) — higher means less changed
    hunk_count: int
    max_hunk_size: int  # line count of the largest hunk
    teaching: str = ""


# ---------------------------------------------------------------------------
# Parser — unified diff reader (lenient: never raises, no-hunk -> [])
# ---------------------------------------------------------------------------

# A leading space is tolerated on the header itself. A model told "every line
# starts with exactly one marker character" applies that rule to the @@ line
# too and emits " @@ -1,4 +1,4 @@" — measured on a live run, where the whole
# patch was then refused as having no header at all. The full header shape is
# still required, so a context line matches only if it is itself an @@ header.
_HUNK_HEADER_RE = re.compile(
    r"^ ?@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$"
)


def parse_diff(text: str) -> List[Hunk]:
    """Unified diff text -> list of Hunk.

    Lenient by design (preserves the historical contract): unparseable input or
    a diff with no `@@` header yields an empty list rather than raising, and a
    header whose declared line counts disagree with the body is still accepted
    (the counts are informational; correctness is enforced by context matching
    at apply time). Optional `---`/`+++`/`diff`/`index` file headers are skipped.
    """
    if not text or not text.strip():
        return []

    hunks: List[Hunk] = []
    current: Optional[Hunk] = None
    lines = text.splitlines()
    i = 0

    # Skip leading file headers if present.
    while i < len(lines) and (
        lines[i].startswith("--- ")
        or lines[i].startswith("+++ ")
        or lines[i].startswith("diff ")
        or lines[i].startswith("index ")
    ):
        i += 1

    while i < len(lines):
        line = lines[i]

        m = _HUNK_HEADER_RE.match(line)
        if m:
            if current is not None:
                hunks.append(current)
            current = Hunk(
                old_start=int(m.group(1)),
                old_count=int(m.group(2)) if m.group(2) else 1,
                new_start=int(m.group(3)),
                new_count=int(m.group(4)) if m.group(4) else 1,
                section=m.group(5).strip(),
            )
            i += 1
            continue

        if current is None:
            # Stray line before the first @@ — skip.
            i += 1
            continue

        if line == "":
            # Blank line = context line some tools trim of trailing whitespace.
            current.lines.append(HunkLine(" ", ""))
            i += 1
            continue

        op = line[0]
        body = line[1:]
        if op in (" ", "+", "-"):
            current.lines.append(HunkLine(op, body))
        elif op == "\\":
            # "\ No newline at end of file" — meta, ignore.
            pass
        else:
            # Unexpected line — the hunk is over.
            break
        i += 1

    if current is not None:
        hunks.append(current)

    return [_unshift(h) for h in hunks]


def normalize_diff(text: str) -> str:
    """Re-emit a diff in the exact shape the engine read it in.

    The parser repairs what models actually write (a shifted hunk, a header
    with a leading space). Everything downstream — the Judge that scores the
    change, the panel that shows it, the editor that applies it — must see the
    SAME diff the engine would apply, or the score on screen belongs to a
    different change than the one being approved. Measured: the repaired patch
    applied cleanly while the Judge, handed the raw text, could not read a
    single added line and scored it 0.

    Returns the input unchanged when there is nothing to parse, so a caller can
    always use the result.
    """
    hunks = parse_diff(text)
    if not hunks:
        return text
    out: List[str] = []
    for h in hunks:
        section = f" {h.section}" if h.section else ""
        out.append(
            f"@@ -{h.old_start},{h.old_count} +{h.new_start},{h.new_count} @@{section}"
        )
        out.extend(f"{line.op}{line.text}" for line in h.lines)
    return "\n".join(out) + "\n"


def _unshift(hunk: Hunk) -> Hunk:
    """Undo a uniform one-column shift of the whole hunk.

    Shown a worked example, models line the markers up under each other and
    emit " -    return 1" / " +    return 2" — every line pushed one column
    right, so each reads as context whose content happens to start with a
    marker. Measured on a live run.

    The correction only applies when the hunk contains NO real '+'/'-' line at
    all (a hunk with no additions and no removals is not a change) and at least
    one shifted one. That combination cannot occur in a well-formed diff, so a
    YAML list or a Markdown bullet — context lines that legitimately begin with
    '-' — is never dedented, because such a hunk still has its own real marker
    lines.
    """
    if not hunk.lines:
        return hunk
    if any(line.op in ("+", "-") for line in hunk.lines):
        return hunk
    shifted = [line for line in hunk.lines if line.text[:1] in ("+", "-")]
    if not shifted:
        return hunk
    hunk.lines = [
        HunkLine(line.text[0], line.text[1:])
        if line.text[:1] in ("+", "-", " ")
        else line
        for line in hunk.lines
    ]
    return hunk


# ---------------------------------------------------------------------------
# Validator — multi-stage, fail-fast (with the workspace sandbox)
# ---------------------------------------------------------------------------

# First-bytes signatures for common binary formats.
_BINARY_SIGNATURES = (
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF8",
    b"PK\x03\x04",
    b"\x7fELF",
    b"%PDF",
    b"\x1f\x8b",
    b"MZ",
)
_MAX_PATCH_LINES = 10000
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_BACKUP_KEEP = 5  # keep the newest N backups per file


def _resolve_workspace_root(explicit: Optional[str]) -> Optional[str]:
    """Workspace sandbox root: explicit arg > env ABS_WORKSPACE_ROOT > none."""
    if explicit:
        return explicit
    env = os.environ.get("ABS_WORKSPACE_ROOT")
    if env:
        return env
    return None


def _within_workspace(file_path: str, workspace_root: str) -> bool:
    """True iff `file_path` resolves to inside `workspace_root` (real paths).

    Uses realpath on both sides so `..` segments and symlinks cannot escape.
    """
    ws_real = os.path.realpath(workspace_root)
    fp_real = os.path.realpath(file_path)
    return fp_real == ws_real or fp_real.startswith(ws_real + os.sep)


def _is_binary(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
        return any(head.startswith(sig) for sig in _BINARY_SIGNATURES)
    except Exception:
        return False


def _prune_old_backups(file_path: str, keep: int = _BACKUP_KEEP) -> int:
    """Keep the newest `keep` `<file>.patch-backup.<ts>` files, delete the rest.

    Failures are swallowed — backup cleanup must never block an edit.
    """
    try:
        directory = os.path.dirname(file_path) or "."
        base = os.path.basename(file_path) + ".patch-backup."
        candidates = []
        for fn in os.listdir(directory):
            if fn.startswith(base):
                full = os.path.join(directory, fn)
                try:
                    candidates.append((os.path.getmtime(full), full))
                except OSError:
                    pass
        candidates.sort(reverse=True)  # newest first
        removed = 0
        for _, path in candidates[keep:]:
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
        return removed
    except OSError:
        return 0


def _check_policy(file_path: str, hunks: List[Hunk]):
    """Optional patch-policy hook. Returns (allowed, reason, violations, severity).

    ABS ships no policy module today, so this degrades to a permissive pass.
    """
    try:
        from app.patches.policy import check_patch_policy  # type: ignore
    except ImportError:
        try:
            from patch_policy import check_patch_policy  # type: ignore
        except ImportError:
            return True, "", [], "ok"
    try:
        with open(file_path) as fh:
            file_line_count = sum(1 for _ in fh)
    except OSError:
        file_line_count = 0
    pol = check_patch_policy(file_path, hunks, file_line_count=file_line_count)
    return pol.allowed, pol.reason, pol.violations, pol.severity


def validate(
    file_path: str,
    diff_text: str,
    *,
    workspace_root: Optional[str] = None,
) -> ValidationResult:
    """Multi-stage patch validator — returns on the first failure.

    Stages: syntax -> size -> path -> WORKSPACE SANDBOX -> exists/readable ->
    binary -> file-size -> policy.
    """
    t0 = time.time()

    # 1. Diff syntax.
    hunks = parse_diff(diff_text)
    if not hunks:
        return ValidationResult(False, "no @@ hunk header found", "syntax")

    total_lines = sum(len(h.lines) for h in hunks)
    if total_lines > _MAX_PATCH_LINES:
        return ValidationResult(
            False,
            f"patch too large: {total_lines} lines (limit {_MAX_PATCH_LINES})",
            "size",
            {"lines": total_lines},
        )

    # 2. Path.
    if not file_path:
        return ValidationResult(False, "file_path is empty", "path")

    ws_root = _resolve_workspace_root(workspace_root)
    if not os.path.isabs(file_path):
        if ws_root:
            file_path = os.path.join(ws_root, file_path)
        else:
            return ValidationResult(
                False, f"file_path must be absolute: {file_path}", "path"
            )
    file_path = os.path.normpath(file_path)

    # 3. Workspace sandbox — the multi-tenant / desktop-workspace boundary.
    if ws_root and not _within_workspace(file_path, ws_root):
        return ValidationResult(
            False,
            f"path is outside the workspace sandbox: {file_path}",
            "sandbox",
            {"workspace_root": os.path.realpath(ws_root)},
        )

    # 4. Exists + readable (new-file creation is a later feature).
    if not os.path.exists(file_path):
        return ValidationResult(False, f"no such file: {file_path}", "path")
    if not os.access(file_path, os.R_OK):
        return ValidationResult(False, f"file not readable: {file_path}", "permission")

    # 5. Binary guard.
    if _is_binary(file_path):
        return ValidationResult(False, "refusing to patch a binary file", "binary")

    # 6. File size sanity.
    try:
        sz = os.path.getsize(file_path)
        if sz > _MAX_FILE_SIZE:
            return ValidationResult(
                False,
                f"file too large: {sz / 1024 / 1024:.1f} MB (limit 10 MB)",
                "size",
            )
    except OSError as exc:
        return ValidationResult(False, f"stat failed: {exc}", "permission")

    # 7. Policy — mass-deletion / dangerous-pattern / critical-file guard.
    allowed, reason, violations, severity = _check_policy(file_path, hunks)
    if not allowed:
        return ValidationResult(
            False, reason, "policy", {"violations": violations, "severity": severity}
        )

    ok_msg = "OK" + (" (warn)" if severity == "warn" else "")
    return ValidationResult(
        True,
        ok_msg,
        "",
        {
            "hunks": len(hunks),
            "lines": total_lines,
            "file_path": file_path,
            "policy_violations": violations,
            "policy_severity": severity,
            "elapsed": round(time.time() - t0, 3),
        },
    )


# ---------------------------------------------------------------------------
# In-memory applier — hunk-by-hunk, context-verified
# ---------------------------------------------------------------------------

class AmbiguousHunkError(ValueError):
    """A hunk's context matches at two-plus places — refusing is the answer.

    Kept distinct from plain ValueError so dry_run does NOT fall through to
    `git apply --check`, whose fuzzy matcher would happily pick one of the
    candidates and report success — the exact guess this engine refuses to make.
    """


def _dedent_one_space(lines: List[HunkLine]) -> Optional[List[HunkLine]]:
    """Drop one leading space from every line of a hunk, or None if that is not
    what is wrong with it.

    Models write ``- def helper():`` — marker, then a courtesy space, then the
    code — where the format allows exactly one marker character followed by the
    line's real content. Every line then carries a phantom indent and nothing
    matches the file. The shift is only undone when it is UNIFORM (every
    non-empty line starts with a space), and the caller still requires a unique
    content match afterwards, so a genuinely indented hunk is never silently
    re-indented.
    """
    if not lines:
        return None
    if not any(hl.text.strip() for hl in lines):
        return None
    if not all(hl.text.startswith(" ") or not hl.text.strip() for hl in lines):
        return None
    return [
        HunkLine(hl.op, hl.text[1:] if hl.text.startswith(" ") else hl.text)
        for hl in lines
    ]


def _trim_trailing_blank_context(lines: List[HunkLine]) -> List[HunkLine]:
    """Drop a trailing run of blank context lines from a hunk.

    Models habitually end a hunk with a blank context line — an artifact of the
    trailing newline, not a real line of the file. At end-of-file that phantom
    line has nothing to match, and a strict engine rejects an otherwise
    byte-exact patch. Only ever used as a RETRY after the untrimmed hunk failed
    to place, so a genuine blank line in the middle is still required.
    """
    out = list(lines)
    while out and out[-1].is_ctx and out[-1].text == "":
        out.pop()
    return out


def _blank_context_before_adds_to_adds(
    lines: List[HunkLine],
) -> Optional[List[HunkLine]]:
    """Turn blank context lines just before the trailing insertions into
    insertions themselves.

    The sibling artifact to a *trailing* blank context: a model appending to a
    file writes the separator blank line as context (` `) because it pictures
    the file ending with one, then puts its `+` lines after it. The file has no
    such line, so the old block is one phantom line too long and a strict
    engine rejects a patch whose intended NEW content is perfectly clear.
    Converting ` ` to `+` for those blanks reproduces that intent exactly —
    the blank line ends up in the file, where the model meant it to be. Only
    ever used as a RETRY after the literal hunk failed to place.
    """
    out = list(lines)
    i = len(out) - 1
    while i >= 0 and out[i].is_add:
        i -= 1
    changed = False
    while i >= 0 and out[i].is_ctx and out[i].text == "":
        out[i] = HunkLine(op="+", text="")
        changed = True
        i -= 1
    return out if changed else None


def _hunk_old_block(h: Hunk, lines: Optional[List[HunkLine]] = None) -> List[str]:
    """The lines a hunk expects to find in the source (context + deletions)."""
    return [hl.text for hl in (lines if lines is not None else h.lines) if not hl.is_add]


def _block_matches_at(source_lines: List[str], block: List[str], at: int) -> bool:
    if at < 0 or at + len(block) > len(source_lines):
        return False
    return all(
        source_lines[at + i].rstrip("\n") == block[i] for i in range(len(block))
    )


def _locate_hunk(
    source_lines: List[str], h: Hunk, src_idx: int, block: Optional[List[str]] = None
) -> int:
    """Where the hunk's old block actually sits.

    The declared position wins when it matches. Otherwise the block is searched
    from the cursor forward — models routinely mis-number `@@ -N` headers, and a
    positionally-strict engine rejects diffs whose content is exact (the editor's
    local applier already relocates; the server must agree with it). The match
    must be UNIQUE: zero or two-plus candidates raise instead of guessing.
    """
    block = block if block is not None else _hunk_old_block(h)
    declared = h.old_start - 1  # 0-indexed
    if not block:
        # pure-insertion hunk: trust the declared spot, clamped into range
        return min(max(declared, src_idx), len(source_lines))
    if declared >= src_idx and _block_matches_at(source_lines, block, declared):
        return declared
    found = -1
    for i in range(src_idx, len(source_lines) - len(block) + 1):
        if _block_matches_at(source_lines, block, i):
            if found != -1:
                raise AmbiguousHunkError(
                    f"hunk @@ -{h.old_start} is ambiguous: its context matches "
                    f"at lines {found + 1} and {i + 1}; refusing to guess"
                )
            found = i
    if found == -1:
        raise ValueError(
            f"hunk @@ -{h.old_start} does not match the file content "
            "(declared position wrong and no unique relocation target)"
        )
    return found


def _place_repaired_hunk(
    source_lines: List[str], h: Hunk, src_idx: int
) -> Tuple[int, List[HunkLine]]:
    """Place a hunk the strict pass could not, by undoing model artifacts.

    Repairs are tried in order and COMBINED (a diff often carries both): drop
    the trailing blank context, undo a uniform one-space shift, or both. Every
    candidate is placed through :func:`_locate_hunk`, so it must still match the
    file uniquely — a repair widens what the engine can read, never what it is
    willing to assume. Raises the strict failure if nothing places.
    """
    candidates: List[List[HunkLine]] = []
    trimmed = _trim_trailing_blank_context(h.lines)
    if len(trimmed) != len(h.lines):
        candidates.append(trimmed)
    bases = [h.lines, trimmed] if len(trimmed) != len(h.lines) else [h.lines]
    for base in bases:
        converted = _blank_context_before_adds_to_adds(base)
        if converted is not None:
            candidates.append(converted)
    for base in list(bases) + [c for c in candidates if c is not None]:
        dedented = _dedent_one_space(base)
        if dedented is not None:
            candidates.append(dedented)

    for lines in candidates:
        if not lines:
            continue
        try:
            target = _locate_hunk(source_lines, h, src_idx, _hunk_old_block(h, lines))
        except AmbiguousHunkError:
            raise
        except ValueError:
            continue
        return target, lines

    # Source-aware last resort — the "content as context" artifact. Asked to
    # append, small models emit the file they intend as PURE context (no +/-
    # at all), or let their context run past the end of the file. If a prefix
    # of the old block matches the file ending exactly at end-of-file, the
    # leftover context lines have nothing left to match — they can only be
    # insertions. The placement is pinned by the file end, so nothing is
    # guessed; a deletion past EOF is a real mismatch and stays a refusal.
    block = _hunk_old_block(h)
    for k in range(len(block) - 1, 0, -1):
        pos = len(source_lines) - k
        if pos < max(src_idx, 0):
            continue
        if not _block_matches_at(source_lines, block[:k], pos):
            continue
        repaired: List[HunkLine] = []
        seen = 0
        ok = True
        for hl in h.lines:
            if hl.is_add:
                repaired.append(hl)
                continue
            seen += 1
            if seen <= k:
                repaired.append(hl)
            elif hl.is_ctx:
                repaired.append(HunkLine(op="+", text=hl.text))
            else:
                ok = False
                break
        if ok:
            return pos, repaired
        break

    raise ValueError(
        f"hunk @@ -{h.old_start} does not match the file content "
        "(no unique placement, with or without diff-format repairs)"
    )


def _apply_hunks_inmem(
    source_lines: List[str],
    hunks: List[Hunk],
    placed: Optional[List[Tuple[int, List[HunkLine]]]] = None,
) -> List[str]:
    """Apply hunks to source lines in order. Context mismatch -> ValueError.

    Unified-diff semantics: `old_start` is 1-indexed; context and '-' lines must
    match the source, '+' lines are inserted, '-' lines are dropped. Hunks whose
    declared position is wrong are relocated to their unique content match
    (see _locate_hunk); ambiguity is an error, never a guess.

    When `placed` is given, each hunk's final placement — its 0-indexed target
    and the (possibly repaired) lines that actually applied — is appended to
    it, so a caller can re-emit the diff the engine really used.
    """
    result: List[str] = []
    src_idx = 0  # 0-indexed cursor into source

    for h in hunks:
        hunk_lines = list(h.lines)
        try:
            target = _locate_hunk(source_lines, h, src_idx)
        except AmbiguousHunkError:
            raise
        except ValueError:
            # The hunk's content is right but its shape carries a model
            # artifact. Try each known repair; each one still has to land on a
            # UNIQUE content match, so none of them is a guess. If none places
            # the hunk, the original failure stands.
            target, hunk_lines = _place_repaired_hunk(source_lines, h, src_idx)
        if placed is not None:
            placed.append((target, list(hunk_lines)))
        while src_idx < target:
            if src_idx >= len(source_lines):
                raise ValueError(f"source too short: hunk @@ -{h.old_start} unreachable")
            result.append(source_lines[src_idx])
            src_idx += 1

        for hl in hunk_lines:
            if hl.is_ctx:
                if src_idx >= len(source_lines):
                    raise ValueError(
                        f"extra context: at line {src_idx + 1} past end of file"
                    )
                if source_lines[src_idx].rstrip("\n") != hl.text:
                    raise ValueError(
                        f"context mismatch at line {src_idx + 1}: "
                        f"expected {hl.text!r}, found {source_lines[src_idx].rstrip()!r}"
                    )
                result.append(source_lines[src_idx])
                src_idx += 1
            elif hl.is_del:
                if src_idx >= len(source_lines):
                    raise ValueError(f"extra delete: at line {src_idx + 1} past end")
                if source_lines[src_idx].rstrip("\n") != hl.text:
                    raise ValueError(
                        f"delete mismatch at line {src_idx + 1}: "
                        f"expected {hl.text!r}, found {source_lines[src_idx].rstrip()!r}"
                    )
                src_idx += 1  # drop the old line
            elif hl.is_add:
                result.append(hl.text + "\n")

    while src_idx < len(source_lines):
        result.append(source_lines[src_idx])
        src_idx += 1

    return result


# ---------------------------------------------------------------------------
# Dry-run — in-memory apply, `git apply --check` fallback
# ---------------------------------------------------------------------------

def _emit_placed_diff(placed: List[Tuple[int, List[HunkLine]]]) -> str:
    """Re-emit a diff from resolved placements, with honest headers.

    Counts are recomputed from the lines that actually applied and starts from
    where they applied, so the text round-trips through a strict applier —
    including the editor's own, which never saw the engine's repairs.
    """
    out: List[str] = []
    delta = 0  # running new-file offset from earlier hunks
    for target, lines in placed:
        old_count = sum(1 for l in lines if not l.is_add)
        new_count = sum(1 for l in lines if not l.is_del)
        old_start = target + 1 if old_count else target
        new_start = old_start + delta if new_count else old_start + delta
        out.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")
        out.extend(f"{l.op}{l.text}" for l in lines)
        delta += new_count - old_count
    return "\n".join(out) + "\n" if out else ""


def dry_run(
    file_path: str,
    diff_text: str,
    *,
    workspace_root: Optional[str] = None,
) -> DryRunResult:
    """Can the patch apply? The file is never touched."""
    v = validate(file_path, diff_text, workspace_root=workspace_root)
    if not v.valid:
        return DryRunResult(False, "validate", "", v.reason)

    file_path = v.meta.get("file_path", file_path)
    hunks = parse_diff(diff_text)

    # Method 1: in-memory apply (no external tool needed).
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            source_lines = fh.readlines()
        placed: List[Tuple[int, List[HunkLine]]] = []
        patched = _apply_hunks_inmem(source_lines, hunks, placed)
        preview = "".join(patched[:50])
        if len(patched) > 50:
            preview += f"\n... ({len(patched) - 50} more lines)"
        return DryRunResult(
            True, "inmemory", preview, "", repaired_diff=_emit_placed_diff(placed)
        )
    except AmbiguousHunkError as exc:
        # Deliberate refusal — git's fuzzy matcher would guess; we don't.
        return DryRunResult(False, "inmemory", "", str(exc))
    except ValueError:
        pass  # fall through to git
    except Exception as exc:
        return DryRunResult(False, "inmemory", "", f"unexpected: {exc}")

    # Method 2: git apply --check (if git is present).
    patch_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".patch", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(f"--- a/{os.path.basename(file_path)}\n")
            tmp.write(f"+++ b/{os.path.basename(file_path)}\n")
            tmp.write(diff_text)
            patch_path = tmp.name
        r = subprocess.run(
            ["git", "apply", "--check", "-p1", patch_path],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.path.dirname(file_path),
        )
        if r.returncode == 0:
            return DryRunResult(True, "git", "", "")
        return DryRunResult(False, "git", "", r.stderr.strip() or r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    except Exception as exc:
        return DryRunResult(False, "git", "", f"git apply error: {exc}")
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except OSError:
                pass

    return DryRunResult(
        False, "all-failed", "", "no method (inmemory/git) could apply the patch"
    )


# ---------------------------------------------------------------------------
# Apply — atomic write + backup + AST validation with rollback
# ---------------------------------------------------------------------------

def apply(
    file_path: str,
    diff_text: str,
    backup: bool = True,
    *,
    workspace_root: Optional[str] = None,
) -> ApplyResult:
    """Apply the patch: validate -> apply -> atomic write -> AST check.

    A `.py` file that fails to re-parse is rolled back from its backup.
    """
    t0 = time.time()

    v = validate(file_path, diff_text, workspace_root=workspace_root)
    if not v.valid:
        return ApplyResult(False, file_path, reason=f"{v.stage}: {v.reason}")

    file_path = v.meta.get("file_path", file_path)
    hunks = parse_diff(diff_text)

    backup_path: Optional[str] = None
    if backup:
        backup_path = f"{file_path}.patch-backup.{int(t0)}"
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as exc:
            return ApplyResult(False, file_path, reason=f"backup failed: {exc}")

    # In-memory apply (context-verified).
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            source_lines = fh.readlines()
        patched_lines = _apply_hunks_inmem(source_lines, hunks)
    except ValueError as exc:
        return ApplyResult(
            False, file_path, backup_path=backup_path, reason=f"apply failed: {exc}"
        )

    # Atomic write (temp + rename).
    tmp_path = f"{file_path}.patch-tmp.{int(t0)}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.writelines(patched_lines)
        os.replace(tmp_path, file_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return ApplyResult(
            False, file_path, backup_path=backup_path, reason=f"write failed: {exc}"
        )

    # AST validation for Python (JS/TS via tree-sitter is a later phase).
    if os.path.splitext(file_path)[1].lower() == ".py":
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                ast.parse(fh.read())
        except SyntaxError as exc:
            if backup_path and os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
            return ApplyResult(
                False,
                file_path,
                backup_path=backup_path,
                reason=f"AST parse failed, rolled back: {exc}",
            )

    if backup:
        _prune_old_backups(file_path)

    return ApplyResult(
        success=True,
        file_path=file_path,
        backup_path=backup_path,
        hunks_applied=len(hunks),
        lines_added=sum(h.adds for h in hunks),
        lines_deleted=sum(h.dels for h in hunks),
        elapsed=round(time.time() - t0, 3),
    )


# ---------------------------------------------------------------------------
# Score — deterministic quality metrics (LLM judge is a separate module)
# ---------------------------------------------------------------------------

def score(diff_text: str) -> ScoreResult:
    """Score a patch 0-10 with human-readable teaching feedback.

    Metrics: minimal_ratio (context share — higher is more minimal), hunk_count
    (fewer is more concentrated), max_hunk_size (a huge hunk smells like a
    rewrite).
    """
    hunks = parse_diff(diff_text)
    if not hunks:
        return ScoreResult(0.0, 0.0, 0, 0, "no valid hunk — check the unified diff format")

    total_adds = sum(h.adds for h in hunks)
    total_dels = sum(h.dels for h in hunks)
    total_ctx = sum(h.ctx for h in hunks)
    total = total_ctx + total_adds + total_dels
    minimal_ratio = total_ctx / total if total else 1.0

    max_hunk_size = max((len(h.lines) for h in hunks), default=0)
    hunk_count = len(hunks)

    s = 10.0
    if hunk_count > 5:
        s -= min(2.0, (hunk_count - 5) * 0.3)
    if max_hunk_size > 50:
        s -= min(2.0, (max_hunk_size - 50) * 0.05)
    if minimal_ratio < 0.3:
        s -= 2.0
    elif minimal_ratio < 0.5:
        s -= 1.0
    s = max(0.0, round(s, 1))

    teaching_bits = []
    if hunk_count > 5:
        teaching_bits.append(f"{hunk_count} hunks — scattered change, keep it concentrated")
    if max_hunk_size > 50:
        teaching_bits.append(f"largest hunk is {max_hunk_size} lines — smells like a rewrite")
    if minimal_ratio < 0.3:
        teaching_bits.append(
            f"context is {minimal_ratio:.0%} — too many lines changed, not a minimal patch"
        )
    if not teaching_bits:
        teaching_bits.append(
            f"minimal patch ({hunk_count} hunk, {total_adds}+ / {total_dels}-)"
        )

    return ScoreResult(
        score=s,
        minimal_ratio=round(minimal_ratio, 3),
        hunk_count=hunk_count,
        max_hunk_size=max_hunk_size,
        teaching=" | ".join(teaching_bits),
    )


# ---------------------------------------------------------------------------
# Back-compat dict wrappers (stable public API for the MCP tools)
# ---------------------------------------------------------------------------

def preview_patch(
    file_path: str, diff_text: str, *, workspace_root: Optional[str] = None
) -> dict:
    """Dry-run the patch without touching the file. Returns {success, reason, ...}."""
    r = dry_run(file_path, diff_text, workspace_root=workspace_root)
    return {
        "success": r.success,
        "reason": r.reason,
        "method": r.method,
        "preview": r.preview,
    }


def apply_patch(
    file_path: str,
    diff_text: str,
    backup: bool = True,
    *,
    workspace_root: Optional[str] = None,
) -> dict:
    """Apply the patch with an atomic write. Returns {success, reason, backup_path, ...}."""
    r = apply(file_path, diff_text, backup=backup, workspace_root=workspace_root)
    return {
        "success": r.success,
        "reason": r.reason,
        "backup_path": r.backup_path,
        "hunks_applied": r.hunks_applied,
        "lines_added": r.lines_added,
        "lines_deleted": r.lines_deleted,
    }


def score_patch(diff_text: str) -> dict:
    """Score a diff 0-10 on minimalism, hunk concentration and size."""
    r = score(diff_text)
    return {
        "score": r.score,
        "hunk_count": r.hunk_count,
        "minimal_ratio": r.minimal_ratio,
        "max_hunk_size": r.max_hunk_size,
        "teaching": r.teaching,
    }
