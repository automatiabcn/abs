# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor's agent: one developer message becomes a run of tool calls.

Until 2026-09-01 the editor chat was a single call — pick a few files by
keyword, put them in the prompt, answer. A transcript from that day shows
what that costs: the model asked the developer to paste `app/routes.py`
four times while the file sat in the open project; "I made the change,
check it" could not be checked; "you write the file" produced a code block;
and a question about a cart total was answered with a route that does not
exist. None of those are prompt problems. The model had no way to look.

This package is the way to look. The loop is driven by the editor (the
files are on the developer's machine and stay there); the server does one
*step* at a time — assemble the prompt, ask the cascade, decide whether the
reply is a tool call or the answer — and the editor runs the tool and comes
back with the result. Two tools run on the server because they need what
the server has: `semantic_search` (the index) and `propose_edit` (the patch
engine and the judge).

    tools.py     — the catalogue: what the model may call, where it runs
    protocol.py  — how a reply is read: a tool call, or the answer
    context.py   — what goes into the prompt each step
    edits.py     — propose_edit: search/replace → diff → validate → judge
    search.py    — semantic_search over the open project
    step.py      — one step of the loop, as a stream of events
"""
