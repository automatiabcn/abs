# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Build the diff ourselves instead of asking a model to write one.

Measured on 2026-08-02 against the free tiers ABS routes to by default: three
Composer proposals in a row were refused by the patch engine, and all three
refusals were correct. The models had written diffs with context lines that
are not in the file, indentation shifted by four spaces, and hunk headers
whose line counts did not match their bodies. `git apply` rejects them, and
so does ours — even with whitespace tolerance.

The prompt was not the problem. It already specified the format, warned about
indentation and carried a worked example; the models still got it wrong. A
unified diff is a machine format with byte-exact obligations, and asking a
language model to satisfy them is asking the wrong thing of it.

So we stop asking. The model returns the file as it should end up, which is a
thing models are good at, and this module diffs it against what is actually on
disk. A diff computed from the real bytes applies by construction — there is
no context to get wrong, because the context is read rather than recalled.

This is the same trade the inline edit (⌘K) has always made, and it is why
that path applies while Composer's did not.
"""

from __future__ import annotations

import difflib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def read_text(path: str) -> Optional[str]:
    """The file as it is, or None when it cannot be read.

    None is not "empty file" — a file we could not read is a file we must not
    pretend to diff against, or we would produce a patch that deletes it.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


# Below this many lines a ratio means nothing: losing 4 of 6 lines is an
# ordinary edit, and a ratio test would refuse it.
_MIN_LINES_FOR_RATIO = 20
# How much of a file an answer may drop before it stops being believable. A
# refactor that removes 30% is normal; one that removes 70% in a single
# proposal is the shape of a reply that stopped early.
_MAX_SHRINK = 0.5


def _looks_truncated(old_text: str, new_text: str) -> bool:
    old_n = len(old_text.splitlines())
    if old_n < _MIN_LINES_FOR_RATIO:
        return False
    return len(new_text.splitlines()) < old_n * _MAX_SHRINK


def diff_from_new_content(
    rel_path: str,
    old_text: Optional[str],
    new_text: str,
) -> str:
    """A unified diff turning `old_text` into `new_text`.

    Returns "" when there is nothing to do, so a model that echoes the file
    back unchanged produces no edit rather than an empty hunk the engine has
    to reason about.
    """
    if old_text is None:
        return ""
    # Models routinely drop or add the trailing newline. That alone is not a
    # change worth proposing, and it would otherwise show up as a whole-file
    # rewrite in the editor.
    if old_text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    if new_text == old_text:
        return ""

    # An answer that lost most of the file is a truncated reply, not an edit.
    # Models are asked for the COMPLETE file and routinely return the
    # interesting part and stop. Believing them turns a cut-off answer into a
    # clean, applicable, dry-run-approved deletion: measured 08-02 across eight
    # tasks, +20/-784 among them. Deleting a file's contents is a real thing to
    # want and it is also exactly what truncation looks like, so where the two
    # cannot be told apart the product refuses rather than guesses.
    if _looks_truncated(old_text, new_text):
        logger.info(
            "composer refused a suspiciously short %s: %d lines -> %d",
            rel_path, old_text.count("\n"), new_text.count("\n"),
        )
        return ""

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        n=3,
    )
    text = "".join(diff)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def edit_diff(
    raw: dict,
    *,
    rel_path: str,
    abs_path: str,
) -> tuple[str, bool]:
    """The diff for one proposed edit, and whether we built it ourselves.

    A model may still return `unified_diff` — older prompts, other callers —
    and that path is left intact. But when it returns the finished content we
    prefer it, because that diff cannot fail to apply for a reason the model
    invented.
    """
    new_text = raw.get("new_content")
    if isinstance(new_text, str) and new_text.strip():
        built = diff_from_new_content(rel_path, read_text(abs_path), new_text)
        if built:
            return built, True
        # An unchanged file is not a failure to fall through from: the model
        # said the file is already right, and it may be.
        if read_text(abs_path) is not None:
            return "", True
    return str(raw.get("unified_diff") or ""), False


def relative_to(workspace_root: str, path: str) -> str:
    """The path as the diff headers should carry it."""
    if os.path.isabs(path):
        try:
            return os.path.relpath(path, workspace_root)
        except ValueError:
            return os.path.basename(path)
    return path
