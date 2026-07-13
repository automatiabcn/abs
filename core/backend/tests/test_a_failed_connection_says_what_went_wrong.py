# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""When an external MCP server will not connect, say why.

The MCP transports run inside an anyio task group, so nearly every real failure —
connection refused, a 307 because the URL wanted a trailing slash, a 401 from an
expired token — comes back wrapped in an ExceptionGroup. The client's catch-all
formatted the wrapper:

    ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)

That string went into `last_error`, onto the server's row, and onto the screen
beside a red dot. The operator has just pasted a URL and pressed "test"; this
tells them nothing at all, and specifically it does not tell them the one thing
that is usually true — that they got the address slightly wrong.

A failure message that cannot be acted on is a failure to report the failure.
"""

from __future__ import annotations


from app.mcp.external.client import _describe


def test_the_real_cause_is_reported_not_the_wrapper():
    inner = ConnectionRefusedError("[Errno 61] Connect call failed ('127.0.0.1', 1)")
    group = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    described = _describe(group)

    assert "ConnectionRefusedError" in described
    assert "Connect call failed" in described
    assert "TaskGroup" not in described, (
        "the operator is being shown the plumbing instead of the problem"
    )


def test_a_cause_nested_two_groups_deep_is_still_found():
    inner = RuntimeError("Redirect response '307 Temporary Redirect'")
    described = _describe(ExceptionGroup("outer", [ExceptionGroup("inner", [inner])]))
    assert "RuntimeError" in described
    assert "307" in described


def test_a_plain_exception_survives_untouched():
    assert _describe(ValueError("bad url")) == "ValueError: bad url"


def test_an_exception_with_no_message_still_names_itself():
    assert _describe(TimeoutError()) == "TimeoutError"


def test_a_pathological_nest_terminates():
    """Malformed or self-referential groups must not hang the connect button."""
    exc: BaseException = ValueError("root")
    for _ in range(50):
        exc = ExceptionGroup("wrap", [exc])
    described = _describe(exc)
    assert described  # it stopped, and it said something
