# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What the model sees at each step, and in what order.

The prompt is one string (the adapters take a prompt, not a message list),
built the way a mid-size model reads best: standing instructions first,
the question last, the bulky material in the middle.

    1. instructions        — who you are, the protocol, the rules that were
                             visibly missing on screen (language by name,
                             never ask for a file, never leak reasoning)
    2. tools               — the catalogue for this mode
    3. project rules       — .abs/rules.md / AGENTS.md
    4. editor state        — open file + cursor, selection, diagnostics,
                             recent files, git status: the context the
                             developer should never have to @-mention
    5. plan                — the task list from earlier turns
    6. files already read  — step 1 retrieval, so the first step is not
                             spent asking for the obvious
    7. conversation so far — earlier turns, summarised past a budget
    8. this run so far     — tool calls and their results, oldest compressed
    9. the developer's message

Every section has a budget, and the budgets are applied from the bottom
up: the message and the latest tool result are never cut; the oldest tool
results and the earliest history go first.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.chat import language as lang
from app.editor_agent import tools as toolbox


class EditorState(BaseModel):
    """What the editor knows about the developer's moment. All optional; an
    older editor sends none of it and the agent still works."""

    active_file: str = ""
    active_language: str = ""
    cursor_line: Optional[int] = None
    selection: str = Field(default="", max_length=8000)
    selection_range: str = ""
    visible_excerpt: str = Field(default="", max_length=8000)
    open_files: List[str] = Field(default_factory=list, max_length=20)
    recent_files: List[str] = Field(default_factory=list, max_length=12)
    diagnostics: List[str] = Field(default_factory=list, max_length=40)
    git_status: List[str] = Field(default_factory=list, max_length=40)
    last_terminal: str = Field(default="", max_length=3000)


class Todo(BaseModel):
    id: str
    text: str
    status: str = "todo"


class StepRecord(BaseModel):
    """One tool call the editor already ran in this turn, and what came back."""

    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    result: str = Field(default="", max_length=60_000)


# --- budgets (characters; ~4 chars per token on code) ------------------------
# Sized for a free-tier provider: the whole prompt is re-sent every step,
# and Groq's free tier allows ~8k tokens a minute — a 7k-token step means
# one step a minute. Step 1 reads ahead; later steps rely on the tools.
INITIAL_FILES_CHARS = 8_000
INITIAL_FILES_MAX = 3
HISTORY_CHARS = 4_000
RUN_CHARS = 20_000
RESULT_KEEP_LATEST = 7_000
RESULT_KEEP_OLDER = 900
RULES_CHARS = 3_000
LISTING_MAX = 120


INSTRUCTIONS = """\
You are ABS, the coding agent built into this code editor. You work inside the \
developer's open project and you can look at it yourself with the tools below. \
The developer sees each tool call as it happens.

How to work
- Look before you answer. If the question is about the project, read or search \
the relevant files first; do not describe code you have not seen in this \
conversation. Never ask the developer to paste or share a file that is in the \
project — read it with read_file. Never say you cannot access the project.
- When the developer says they changed something and asks you to check it, call \
git_diff first, then read what changed.
- When the developer asks you to write, create, fix or change code, do it with \
propose_edit or create_file (Agent mode) instead of printing the code in the \
chat. Read the file before editing it; copy the `search` text exactly from what \
you read. After an edit, check get_diagnostics (and run_tests when tests exist) \
and fix what you broke.
- For a task with several steps, write the steps with update_plan first, then \
work through them, marking each done. When the developer says "continue", pick \
up the first step that is not done.
- Keep going until the task is done or you truly need a decision from the \
developer (then ask_user with a specific question). Do not stop to ask \
"which would you like?" when the developer already told you to choose.
- Do not call the same tool with the same arguments twice.

Answering
- Lead with the answer; then only the detail that is needed. Short paragraphs \
and lists; the panel is narrow.
- Name places in the project as workspace-relative path with the real line \
number from what you read, e.g. `app/routes.py:42`. Never a placeholder.
- Do not repeat the file contents you read; quote at most the few lines that \
matter. A fenced code block only for code the developer will copy.
- If something is not in what you saw, say so plainly. Never invent a route, \
function, table or file.
- Write only the answer. No notes to yourself, no "We need to…", no reasoning \
before the answer.

Language
- {language_rule}

Reply format
- To call a tool, reply with exactly one JSON object and nothing else:
  {{"tool": "<name>", "args": {{...}}}}
- To answer the developer, write the answer as plain Markdown — no JSON.
- One tool call per reply. You will receive its result and can call another.
"""


def _language_rule(code: str) -> str:
    if code in lang.NAMES:
        return (
            f"The developer writes in {lang.name(code)}. Answer in {lang.name(code)} "
            "— every sentence, including headings and list items. Keep code, "
            "identifiers, paths and command names exactly as they are."
        )
    return (
        "Answer in the language the developer wrote in. Keep code, identifiers "
        "and paths as they are."
    )


# --- intent ----------------------------------------------------------------
def _intent_patterns() -> Dict[str, "re.Pattern[str]"]:
    """The developer's words for 'check it', 'write it', 'go on' in the
    languages they use — data in app/chat/lang_data.json, not code."""
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "chat", "lang_data.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh).get("intents", {})
    except (OSError, ValueError):  # pragma: no cover
        raw = {}
    out: Dict[str, "re.Pattern[str]"] = {}
    for key, pat in raw.items():
        try:
            out[key] = re.compile(pat, re.I)
        except re.error:
            continue
    return out


_INTENTS = _intent_patterns()
_VERIFY = _INTENTS.get("verify", re.compile(r"\b(check|verify)\b", re.I))
_WRITE = _INTENTS.get("write", re.compile(r"\b(write|create|add|fix)\b", re.I))
_CONTINUE = _INTENTS.get("continue", re.compile(r"^\s*(continue|next)\b", re.I))


def detect_intent(message: str) -> str:
    """'continue' | 'verify' | 'write' | 'ask'. A hint the prompt passes on;
    the model may still call any tool."""
    m = message or ""
    if _CONTINUE.search(m) and len(m) < 80:
        return "continue"
    if _VERIFY.search(m):
        return "verify"
    if _WRITE.search(m):
        return "write"
    return "ask"


_INTENT_HINT = {
    "verify": (
        "System hint: the developer says they changed something and wants it "
        "checked. Call git_diff first, read the changed parts, then answer."
    ),
    "write": (
        "System hint: the developer wants code written or changed. Read the "
        "file(s) involved, then use propose_edit / create_file. Do not print "
        "the code as an answer."
    ),
    "continue": (
        "System hint: the developer wants you to continue with the plan. Take "
        "the first step that is not done and do it; do not ask which one."
    ),
}


# --- assembly --------------------------------------------------------------
def _numbered(body: str) -> str:
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(body.splitlines()))


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 200]
    tail = text[-150:]
    return f"{head}\n… [{len(text) - limit} characters cut] …\n{tail}"


def render_editor_state(st: Optional[EditorState]) -> str:
    if st is None:
        return ""
    parts: List[str] = []
    if st.active_file:
        where = f" (cursor at line {st.cursor_line})" if st.cursor_line else ""
        parts.append(f"Open file: {st.active_file}{where}")
    if st.selection.strip():
        rng = f" {st.selection_range}" if st.selection_range else ""
        parts.append(
            f"Selected code in {st.active_file}{rng}:\n```\n{st.selection[:6000]}\n```"
        )
    elif st.visible_excerpt.strip():
        parts.append(
            f"Lines around the cursor in {st.active_file}:\n```\n{st.visible_excerpt[:6000]}\n```"
        )
    if st.open_files:
        parts.append("Other open files: " + ", ".join(st.open_files[:12]))
    if st.recent_files:
        parts.append("Recently edited: " + ", ".join(st.recent_files[:8]))
    if st.diagnostics:
        parts.append("Current problems (linters, language servers):\n" + "\n".join(st.diagnostics[:20]))
    if st.git_status:
        parts.append("git status (uncommitted):\n" + "\n".join(st.git_status[:30]))
    if st.last_terminal.strip():
        parts.append("Last terminal output:\n```\n" + st.last_terminal[-2000:] + "\n```")
    return "\n\n".join(parts)


def render_plan(todos: Sequence[Todo]) -> str:
    if not todos:
        return ""
    mark = {"done": "[x]", "doing": "[~]", "todo": "[ ]"}
    return "\n".join(f"{mark.get(t.status, '[ ]')} {t.id}: {t.text}" for t in todos)


def render_run(steps: Sequence[StepRecord], compact: bool = False) -> str:
    """This turn's tool calls. The two latest results are kept whole (the
    model is reasoning about them now); older ones are clipped; and when
    the turn is still over budget the oldest are reduced to their names."""
    if not steps:
        return ""
    import json

    def block(i: int, s: StepRecord, keep: int) -> str:
        args = json.dumps(s.args, ensure_ascii=False)
        return f"[Step {i + 1}] You called {s.name} {args}\nResult:\n{_clip(s.result, keep)}"

    n = len(steps)
    latest = RESULT_KEEP_LATEST // 2 if compact else RESULT_KEEP_LATEST
    older = 400 if compact else RESULT_KEEP_OLDER
    budget = RUN_CHARS // 2 if compact else RUN_CHARS
    blocks = [
        block(i, s, latest if i >= n - 2 else older)
        for i, s in enumerate(steps)
    ]
    omitted = 0
    while sum(len(b) for b in blocks) > budget and len(blocks) > 2:
        blocks.pop(0)
        omitted += 1
    if omitted:
        names = ", ".join(s.name for s in steps[:omitted])
        blocks.insert(0, f"[{omitted} earlier step(s) not shown: {names}]")
    return "\n\n".join(blocks)


def render_files(files: Sequence[Tuple[str, str]]) -> str:
    out: List[str] = []
    spent = 0
    for rel, body in files[:INITIAL_FILES_MAX]:
        body = body[: max(0, INITIAL_FILES_CHARS - spent)]
        if not body:
            break
        spent += len(body)
        out.append(f"--- {rel} ---\n{_numbered(body)}")
    return "\n\n".join(out)


def repeated_calls(steps: Sequence[StepRecord]) -> List[str]:
    """Tool calls made more than once with the same arguments — the model
    is not converging (live 09-01: grep 'total' three times in a row)."""
    import json

    seen: Dict[str, int] = {}
    out: List[str] = []
    for s in steps:
        sig = f"{s.name} {json.dumps(s.args, sort_keys=True, ensure_ascii=False)}"
        seen[sig] = seen.get(sig, 0) + 1
        if seen[sig] == 2:
            out.append(sig)
    return out


def must_answer(steps: Sequence[StepRecord], max_steps: int) -> bool:
    """When the tools are taken away and the model is told to answer: it has
    repeated itself twice, or it is one call from the budget. Telling it to
    stop was not enough on its own (live 09-01: thirteen greps for 'total');
    withholding the tools is."""
    import json

    n = len(steps)
    counts: Dict[str, int] = {}
    for s in steps:
        sig = f"{s.name} {json.dumps(s.args, sort_keys=True, ensure_ascii=False)}"
        counts[sig] = counts.get(sig, 0) + 1
    worst = max(counts.values(), default=0)
    return worst >= 3 or len(repeated_calls(steps)) >= 2 or n >= max_steps - 1


def budget_note(steps: Sequence[StepRecord], max_steps: int) -> str:
    n = len(steps)
    notes: List[str] = []
    if must_answer(steps, max_steps):
        return (
            "System: no more tool calls are available for this message. Answer the "
            "developer now with what you have found. If the thing they asked about "
            "was not found, say plainly that it is not in the project."
        )
    rep = repeated_calls(steps)
    if rep:
        notes.append(
            "System: you already made this call and its result is above — do not "
            "repeat it: " + "; ".join(rep[-2:]) + ". Use what you have, or try a "
            "different tool or argument."
        )
    if n >= max(3, max_steps - 4):
        notes.append(
            f"System: you have used {n} of {max_steps} tool calls for this message. "
            "If two searches found nothing, the thing is not in the project — say so. "
            "Answer now unless one more call is essential."
        )
    return "\n".join(notes)


def build_prompt(
    *,
    message: str,
    mode: str,
    lang_code: str,
    intent: str,
    project_name: str,
    rules: str,
    rules_from: str,
    listing: Sequence[str],
    files: Sequence[Tuple[str, str]],
    history: str,
    editor: Optional[EditorState],
    plan: Sequence[Todo],
    steps: Sequence[StepRecord],
    repair: str = "",
    max_steps: int = 12,
    native_tools: bool = False,
    compact: bool = False,
) -> str:
    """`native_tools`: the catalogue travels as function definitions, so the
    text names them only (sending both doubled the prompt). `compact`: the
    provider said the request was too large — everything optional shrinks."""
    if native_tools:
        names = ", ".join(t["name"] for t in toolbox.catalogue(mode))
        tools_text = f"Tools (defined as functions you can call): {names}."
    else:
        tools_text = "Tools (name(arguments): purpose; `?` = optional):\n" + toolbox.describe_for_prompt(mode)
    parts: List[str] = [
        INSTRUCTIONS.format(language_rule=_language_rule(lang_code)).strip(),
        tools_text,
    ]
    listing_max = 40 if compact else LISTING_MAX
    history_chars = 1500 if compact else HISTORY_CHARS
    if mode == "ask":
        parts.append(
            "Mode: Ask. You can read anything but not change files. If the developer "
            "asks for a change, show the exact change as a code block and say they "
            "can switch to Agent mode to have it applied."
        )
    else:
        parts.append(
            "Mode: Agent. Edits and commands are shown to the developer and run "
            "after their approval; the tool result tells you what happened."
        )
    if rules.strip():
        where = f" (from {rules_from})" if rules_from else ""
        parts.append(
            f"Project rules{where} — the developer's standing instructions. "
            f"Follow them:\n{rules.strip()[:RULES_CHARS]}"
        )
    if listing:
        where = f" ({project_name})" if project_name else ""
        parts.append(
            f"Files in the project{where}, names only ({min(len(listing), listing_max)} of {len(listing)} shown):\n"
            + "\n".join(list(listing)[:listing_max])
        )
    st = render_editor_state(editor)
    if st:
        parts.append("Editor state right now:\n" + st)
    pl = render_plan(plan)
    if pl:
        parts.append("Task list from earlier in this conversation:\n" + pl)
    if files and not steps and not compact:
        parts.append(
            "Files already read for you (numbered lines). Cite them as path:line:\n\n"
            + render_files(files)
        )
    elif files:
        parts.append(
            "Files that were read for you at the start of this turn: "
            + ", ".join(rel for rel, _ in files[:INITIAL_FILES_MAX])
            + " (read_file again if you need their lines)."
        )
    if history.strip():
        parts.append("Conversation so far:\n" + _clip(history.strip(), history_chars))
    parts.append("The developer says:\n" + message.strip())
    hint = _INTENT_HINT.get(intent)
    if hint and not steps:
        parts.append(hint)
    run = render_run(steps, compact=compact)
    if run:
        parts.append("Your work so far in this turn:\n" + run)
    note = budget_note(steps, max_steps)
    if note:
        parts.append(note)
    if repair:
        parts.append(repair)
    parts.append(
        "Your reply (one JSON tool call, or the answer in "
        f"{lang.name(lang_code) or 'the developer’s language'}):"
    )
    return "\n\n".join(parts)
