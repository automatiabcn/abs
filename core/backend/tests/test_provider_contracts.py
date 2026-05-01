from __future__ import annotations

import copy

import pytest

from app.providers.contract_validator import (
    PROVIDERS,
    assert_canonical_request,
    assert_canonical_response,
    canonical_text,
    fingerprint,
    load_fixture,
)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_request_fixture_loads(provider):
    payload = load_fixture(provider, "request")
    assert isinstance(payload, dict) and payload


@pytest.mark.parametrize("provider", PROVIDERS)
def test_response_fixture_loads(provider):
    payload = load_fixture(provider, "response")
    assert isinstance(payload, dict) and payload


@pytest.mark.parametrize("provider", PROVIDERS)
def test_request_passes_canonical_check(provider):
    assert_canonical_request(provider, load_fixture(provider, "request"))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_response_passes_canonical_check(provider):
    assert_canonical_response(provider, load_fixture(provider, "response"))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_canonical_text_non_empty(provider):
    text = canonical_text(provider, load_fixture(provider, "response"))
    assert isinstance(text, str) and len(text) > 0


def test_request_drift_detected():
    a = load_fixture("groq", "request")
    b = copy.deepcopy(a)
    b["model"] = "different-model"
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_deterministic():
    a = load_fixture("groq", "request")
    assert fingerprint(a) == fingerprint(copy.deepcopy(a))


def test_anthropic_request_missing_messages_raises():
    payload = load_fixture("anthropic", "request")
    payload.pop("messages")
    with pytest.raises(AssertionError, match="messages"):
        assert_canonical_request("anthropic", payload)


def test_gemini_request_empty_parts_raises():
    with pytest.raises(AssertionError):
        assert_canonical_request("gemini", {"contents": [{"parts": []}]})


def test_cohere_response_block_missing_text_raises():
    payload = load_fixture("cohere", "response")
    payload["message"]["content"] = [{"type": "text"}]
    with pytest.raises(AssertionError):
        assert_canonical_response("cohere", payload)


def test_groq_response_missing_choices_raises():
    payload = load_fixture("groq", "response")
    payload.pop("choices")
    with pytest.raises(AssertionError):
        assert_canonical_response("groq", payload)


def test_unknown_provider_request_raises():
    with pytest.raises(AssertionError):
        assert_canonical_request("unknown", {})


def test_unknown_provider_response_raises():
    with pytest.raises(AssertionError):
        assert_canonical_response("unknown", {})


def test_unknown_provider_canonical_text_raises():
    with pytest.raises(AssertionError):
        canonical_text("unknown", {})
