"""A provider rejecting its model's own output is not a dead provider.

Scenarios G1/A1/A2, 2026-08-28: Groq answered a JSON-mode request with
400 `json_validate_failed` (the model produced invalid JSON). The adapter
classed every 400 as permanent, provider_health parked Groq for ten
minutes, the next agent run had no provider, came back degraded, and the
high-risk approval gate was skipped. One bad generation is transient; a
bad key is not.
"""

from __future__ import annotations

import inspect

from app.providers import base

GROQ_JSON_400 = (
    '{"error":{"message":"Failed to validate JSON. Please adjust your prompt. '
    'See \'failed_generation\' for more details.","type":"invalid_request_error",'
    '"code":"json_validate_failed","failed_generation":""}}'
)


def test_json_validate_failed_is_a_generation_failure():
    assert base._is_generation_failure(GROQ_JSON_400) is True


def test_tool_call_parsing_failure_is_one_too():
    # C10, same day: "Parsing failed. The model generated output that could
    # not be parsed." on a tool-call request.
    assert base._is_generation_failure('{"error":{"message":"Parsing failed. The model generated output that could not be parsed. Please adjust your prompt. See \'failed_generation\'"}}') is True


def test_a_bad_key_or_bad_request_is_not():
    assert base._is_generation_failure('{"error":{"message":"invalid api key","code":"invalid_api_key"}}') is False
    assert base._is_generation_failure("model not found") is False
    assert base._is_generation_failure("") is False


def test_the_4xx_mapping_consults_it():
    src = inspect.getsource(base.openai_compatible_chat)
    at = src.index("if r.status_code >= 400:")
    block = src[at : at + 2000]
    assert "transient=_is_generation_failure(r.text)" in block, (
        "the non-stream 4xx raise must classify a generation failure as transient"
    )
