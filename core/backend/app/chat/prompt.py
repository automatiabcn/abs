# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The voice of the editor chat.

Until 2026-08-28 the chat sent the developer's question and a few project
files to the model with no instruction at all — no role, no format, no
language rule. The answers read like a dump: whole docstrings echoed back,
no structure, no reference to where in the project the answer lived. The
model was not wrong; it was never told what kind of answer a side-bar chat
wants.

This module is the one place that says so. It is pure text assembly so it
can be tested without a provider, and it is opt-in (``style="chat"``) so
other callers of ``cascade_ask`` — inline edit, external MCP clients — keep
the bare prompt they rely on.

Providers here take a single prompt string (no system role), so the
instructions are the first thing in the string and the question is the
last: the two ends of a long input are what mid-size open models attend to
best; the file bodies go in the middle where losing a little attention costs
the least.
"""

from __future__ import annotations

from typing import Sequence, Tuple

# Kept short on purpose. Every extra rule is one more the smaller models drop;
# the ones here are the ones whose absence was visible on screen.
CHAT_INSTRUCTIONS = """\
You are ABS, the coding assistant built into this code editor. You are \
talking with the developer in a narrow side panel next to their code.

How to answer
- Lead with the answer. One short paragraph with the conclusion or the fix, \
then only the detail that is needed.
- Do not repeat the code or docstrings you were shown; the developer has them \
open. Quote at most the few lines that matter.
- When you refer to something in the project, name where it is as \
`path/to/file.py:LINE` (workspace-relative). Those references become links.
- Use a fenced code block (```lang) only for code the developer would copy \
or for a concrete change. Use inline `code` for names.
- Prefer short paragraphs and lists over long prose. The panel is narrow.
- If the question is ambiguous or needs a file you were not given, say what \
you would need and ask one short question instead of guessing.

Honesty
- Only describe functions, classes, routes and settings that appear in the \
files you were given or in the conversation. Never invent an API.
- If something is not in what you can see, say so plainly.

Language
- Reply in the language the developer wrote in (Turkish, Spanish, English, \
or any other). Keep code, identifiers and paths as they are.
"""


def chat_prompt(
    question: str,
    *,
    files: Sequence[Tuple[str, str]] = (),
    project_name: str = "",
    history: str = "",
    rules: str = "",
    rules_from: str = "",
    attachments: str = "",
) -> str:
    """Assemble the string the model sees for one chat turn.

    Order: instructions, project rules, conversation so far, project files,
    attachments, question. The question is last because the last lines are
    the ones the model answers; the rules are first because they are the
    developer's standing instructions and outrank everything but ours.
    """
    parts = [CHAT_INSTRUCTIONS.strip()]
    if rules.strip():
        where = f" (from {rules_from})" if rules_from else ""
        parts.append(
            f"Project rules{where} — the developer's standing instructions "
            f"for this project. Follow them:\n{rules.strip()}"
        )
    if history.strip():
        parts.append("Conversation so far:\n" + history.strip())
    if files:
        blocks = "\n\n".join(f"--- {rel} ---\n{body}" for rel, body in files)
        where = f" ({project_name})" if project_name else ""
        parts.append(
            "Files from the project the developer has open"
            f"{where}. Cite them as path:LINE when you use them:\n\n{blocks}"
        )
    if attachments.strip():
        parts.append("Attached by the developer:\n" + attachments.strip())
    parts.append("The developer asks:\n" + question.strip())
    return "\n\n".join(parts)
