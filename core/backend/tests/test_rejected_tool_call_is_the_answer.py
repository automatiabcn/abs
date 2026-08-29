"""A tool call the provider rejected is still the model's answer.

C10, 2026-08-28: agent mode asks for the tool call as JSON text. gpt-oss
writes it as a native function call; Groq, offered no tools, answers 400
`tool_use_failed` — and returns the call in `failed_generation`. Seven such
rejections in one scenario run became "No provider answered". The adapter
now hands that output back as the response, and the loop reads the
provider-native shape {name, arguments} as {"action": "tool", …}.
"""

from __future__ import annotations

import inspect

from app.agentic import loop
from app.providers import base

REJECTION = (
    '{"error":{"message":"Tool choice is none, but model called a tool",'
    '"type":"invalid_request_error","code":"tool_use_failed",'
    '"failed_generation":"{\\"name\\": \\"system_status\\", \\"arguments\\": {}}"}}'
)


def test_the_rejected_generation_is_salvaged():
    assert base._generation_from_rejection(REJECTION) == '{"name": "system_status", "arguments": {}}'


def test_an_empty_or_unrelated_400_is_not():
    assert base._generation_from_rejection('{"error":{"code":"json_validate_failed","failed_generation":""}}') is None
    assert base._generation_from_rejection('{"error":{"message":"invalid api key"}}') is None
    assert base._generation_from_rejection("not json") is None


def test_the_4xx_branch_returns_it_as_the_answer():
    src = inspect.getsource(base.openai_compatible_chat)
    at = src.index("if r.status_code >= 400:")
    block = src[at : at + 1200]
    assert "salvaged = _generation_from_rejection(r.text)" in block
    assert "return ProviderResponse(" in block


def test_the_loop_reads_the_native_tool_call_shape():
    parsed = loop.parse_action('{"name": "system_status", "arguments": {}}')
    assert parsed == {"action": "tool", "name": "system_status", "args": {}}
    parsed = loop.parse_action('{"name": "graph", "arguments": "{\\"query\\": \\"Falcon\\"}"}')
    assert parsed == {"action": "tool", "name": "graph", "args": {"query": "Falcon"}}
    # our own shape is untouched
    assert loop.parse_action('{"action": "final", "answer": "ok"}') == {"action": "final", "answer": "ok"}
