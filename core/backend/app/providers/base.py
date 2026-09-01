# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider base class + the shared OpenAI-compatible chat completions call."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from .schemas import ProviderError, ProviderResponse


# The spellings vendors use to say "I ran out of room". OpenAI-compatible APIs
# say `length`; Anthropic says `max_tokens`; Gemini shouts `MAX_TOKENS`. Same
# fact, three dialects — and a guard that knows only one of them is a guard
# switched off for two thirds of the chain.
_CUT_OFF = {"length", "max_tokens", "max_output_tokens"}





def _generation_from_rejection(body: str) -> Optional[str]:
    """The model's own output from a provider's 'your generation was rejected'
    400, when the provider sent it back — or None."""
    if not _is_generation_failure(body):
        return None
    try:
        err = (json.loads(body) or {}).get("error") or {}
    except (ValueError, TypeError):
        return None
    gen = err.get("failed_generation")
    return gen.strip() if isinstance(gen, str) and gen.strip() else None

def _is_generation_failure(body: str) -> bool:
    """The provider rejected its own model's output, not our request."""
    t = (body or "")[:400]
    return (
        "json_validate_failed" in t
        or "tool_use_failed" in t
        or "failed_generation" in t
        or "could not be parsed" in t
    )

def _retry_after_seconds(r: Any) -> "float | None":
    """The provider's Retry-After, in seconds, when it sent one.

    Groq's free tier answers a per-minute burst with a 429 and a Retry-After
    of a few seconds; a caller that retries sooner than that only gets
    another 429 (CI, 2026-08-28: two in four seconds, then 200 at thirty)."""
    try:
        raw = r.headers.get("retry-after") if getattr(r, "headers", None) is not None else None
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return None

def was_cut_off(finish_reason: Any) -> bool:
    """True when a provider says its answer stopped at the token limit.

    Anything else — "stop", an empty string, a missing field, a provider that
    reports nothing at all — is False. Silence is not evidence of truncation,
    and treating it as such would refuse every answer from the quiet providers.
    """
    if not isinstance(finish_reason, str):
        return False
    return finish_reason.strip().lower() in _CUT_OFF


def read_openai_payload(
    data: Dict[str, Any],
    *,
    provider: str,
    model: str,
    elapsed_ms: int,
) -> ProviderResponse:
    """One OpenAI-compatible response body, normalised.

    Split out of the HTTP call so the parsing can be tested against a payload
    rather than a live provider — and so every OpenAI-shaped provider picks up
    `truncated` by construction instead of by being remembered.
    """
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"{provider} unexpected response: {str(data)[:200]}",
            provider=provider,
            transient=False,
        ) from exc

    usage = data.get("usage") or {}
    return ProviderResponse(
        text=text,
        model=model,
        provider=provider,
        elapsed_ms=elapsed_ms,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        truncated=was_cut_off(choice.get("finish_reason")),
        tool_calls=_tool_calls_of(choice.get("message") or {}),
    )


def _tool_calls_of(message: Dict[str, Any]) -> list:
    """`message.tool_calls` in the OpenAI shape → [{name, arguments}]."""
    out = []
    for tc in message.get("tool_calls") or []:
        fn = (tc or {}).get("function") or {}
        name = fn.get("name")
        if isinstance(name, str) and name:
            args = fn.get("arguments")
            out.append({"name": name, "arguments": args if isinstance(args, str) else json.dumps(args or {})})
    return out


class BaseProvider(ABC):
    """Abstract base every provider client derives from."""

    name: str = "base"
    default_model: str = ""
    default_timeout: float = 30.0

    @abstractmethod
    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Send the prompt to the model, return a normalized ProviderResponse.

        Failures must be raised as ProviderError with `transient` set correctly:
        the cascade uses that flag to decide whether failing over can help.
        """
        raise NotImplementedError

    #: Whether `stream()` delivers the answer as it is produced. A provider
    #: that leaves this False still works through `stream()` — the whole
    #: answer arrives as one piece — and the caller can say so honestly.
    streams: bool = False

    async def stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator["StreamEvent"]:
        """Yield the answer as it is produced: `StreamEvent(delta=...)` pieces,
        then exactly one `StreamEvent(final=ProviderResponse)`.

        The default does not stream — it calls `call()` and hands the text
        over in one piece — so every provider can be driven through this one
        entry point. Errors are raised the same way `call()` raises them.
        """
        resp = await self.call(prompt, model=model, **kwargs)
        if resp.text:
            yield StreamEvent(delta=resp.text)
        yield StreamEvent(final=resp)


class StreamEvent:
    """One step of a streamed answer: a piece of text, or the finished
    response with its accounting. Exactly one of the two is set."""

    __slots__ = ("delta", "final")

    def __init__(
        self, delta: Optional[str] = None, final: Optional[ProviderResponse] = None
    ) -> None:
        self.delta = delta
        self.final = final


async def openai_compatible_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider_name: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: float = 30.0,
    extra_headers: Optional[Dict[str, str]] = None,
    response_format: Optional[dict] = None,
    extra_body: Optional[Dict[str, Any]] = None,
) -> ProviderResponse:
    """Shared call for any OpenAI-compatible /chat/completions endpoint.

    Groq, Cerebras, OpenRouter and vLLM all speak the same schema, so they get
    one implementation and one place where transient-vs-permanent is decided.
    """
    if not api_key:
        raise ProviderError(
            f"{provider_name} API key is not configured",
            provider=provider_name,
            transient=False,
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    # Optional structured-output enforcement (OpenAI/Groq json_object mode).
    # Default None → body unchanged, so existing chat/qual callers are unaffected.
    if response_format:
        body["response_format"] = response_format
    # Provider-specific knobs the schema does not standardise (Groq's
    # `reasoning_effort` is the one that matters today: a reasoning model
    # given 80 tokens spends all of them thinking and answers with nothing —
    # measured live on Tab, 08-18). Callers pass exactly what they mean.
    if extra_body:
        body.update(extra_body)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"{provider_name} timeout ({timeout}s)",
            provider=provider_name,
            transient=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"{provider_name} connection error: {exc}",
            provider=provider_name,
            transient=True,
        ) from exc

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if r.status_code >= 500:
        raise ProviderError(
            f"{provider_name} 5xx: {r.status_code}",
            provider=provider_name,
            transient=True,
        )
    if r.status_code == 429:
        wait = _retry_after_seconds(r)
        raise ProviderError(
            f"{provider_name} rate limit" + (f" (retry after {wait:g}s)" if wait else ""),
            provider=provider_name,
            transient=True,
            retry_after=wait,
        )
    if r.status_code == 413:
        # This request is too big for this provider's window (Groq's free
        # tier: 8000 tokens a minute; a Composer prompt with whole files is
        # more). The next provider gets it; the key is fine and must not be
        # marked dead for ten minutes over one large prompt (live, 08-28).
        raise ProviderError(
            f"{provider_name} request too large for its window",
            provider=provider_name,
            transient=True,
        )
    if r.status_code >= 400:
        # Groq rejects a tool call the model made when no tools were offered
        # ("Tool choice is none, but model called a tool") — and puts the
        # model's actual output in `failed_generation`. For the agent loop,
        # which asks for the tool call as JSON text, that output IS the
        # answer; throwing it away made agent mode say "No provider
        # answered" seven times in one scenario run (C10, 2026-08-28).
        salvaged = _generation_from_rejection(r.text)
        if salvaged:
            return ProviderResponse(
                text=salvaged, model=model, provider=provider_name, elapsed_ms=elapsed_ms
            )
        raise ProviderError(
            f"{provider_name} {r.status_code}: {r.text[:200]}",
            provider=provider_name,
            # A 400 is usually the key or the request — permanent for this
            # provider. Not when the provider says the MODEL's output failed
            # its own JSON validation (Groq `json_validate_failed`): that is
            # one generation gone wrong, not a dead provider, and marking it
            # permanent parked Groq for ten minutes and turned a high-risk
            # agent's approval gate off (scenarios G1/A1/A2, 2026-08-28).
            transient=_is_generation_failure(r.text),
        )

    try:
        data = r.json()
    except ValueError as exc:
        raise ProviderError(
            f"{provider_name} JSON parse error", provider=provider_name, transient=True
        ) from exc

    return read_openai_payload(
        data, provider=provider_name, model=model, elapsed_ms=elapsed_ms
    )


def _finish_stream_status(r: "httpx.Response", provider_name: str) -> None:
    """The same status-to-error mapping as the blocking call, applied before a
    single byte of the body is read — so a failed leg fails over exactly as it
    would have without streaming."""
    if r.status_code >= 500:
        raise ProviderError(
            f"{provider_name} 5xx: {r.status_code}", provider=provider_name, transient=True
        )
    if r.status_code == 429:
        wait = _retry_after_seconds(r)
        raise ProviderError(
            f"{provider_name} rate limit" + (f" (retry after {wait:g}s)" if wait else ""),
            provider=provider_name,
            transient=True,
            retry_after=wait,
        )
    if r.status_code == 413:
        raise ProviderError(
            f"{provider_name} request too large for its window",
            provider=provider_name,
            transient=True,
        )
    if r.status_code >= 400:
        raise ProviderError(
            f"{provider_name} {r.status_code}", provider=provider_name, transient=False
        )


def parse_openai_stream_line(line: str) -> Optional[Dict[str, Any]]:
    """One SSE line from an OpenAI-compatible stream → its JSON, or None for
    keep-alives, comments and the `[DONE]` sentinel. Pure, so it is tested
    against text rather than a live provider."""
    if not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None


async def openai_compatible_stream(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider_name: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: float = 30.0,
    extra_headers: Optional[Dict[str, str]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[StreamEvent]:
    """The streaming twin of `openai_compatible_chat`.

    Yields `StreamEvent(delta=...)` as the provider produces text and closes
    with `StreamEvent(final=ProviderResponse)` carrying the usage the provider
    reported (`stream_options.include_usage`) and whether the answer was cut
    off. Everything that can go wrong before the first byte raises exactly
    as the blocking call does, so the cascade can fail over; an error after
    text has started is raised too, and the caller decides what to keep.
    """
    if not api_key:
        raise ProviderError(
            f"{provider_name} API key is not configured",
            provider=provider_name,
            transient=False,
        )
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    body: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if extra_body:
        body.update(extra_body)

    start = time.monotonic()
    text_parts: list[str] = []
    finish_reason: Any = None
    usage: Dict[str, Any] = {}
    # Native tool calls arrive as fragments keyed by index; the name comes
    # once, the arguments string in pieces.
    calls: Dict[int, Dict[str, str]] = {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=body) as r:
                if r.status_code >= 400:
                    # Read the body for the message before the mapping raises.
                    await r.aread()
                    _finish_stream_status(r, provider_name)
                async for line in r.aiter_lines():
                    data = parse_openai_stream_line(line)
                    if not data:
                        continue
                    if isinstance(data.get("error"), (dict, str)) and not data.get("choices"):
                        # A 200 stream can still carry the provider's refusal
                        # as its only frame (Groq's rate limit after a retry,
                        # live 09-01). Read as "nothing came back" it became
                        # a blank answer with no failover; it is a failed leg.
                        #
                        # Unless the refusal is of the model's OWN output
                        # ("Tool choice is none, but model called a tool"):
                        # then `failed_generation` IS the answer, exactly as
                        # the blocking call treats it (C10).
                        salvaged = _generation_from_rejection(json.dumps(data))
                        if salvaged:
                            text_parts.append(salvaged)
                            yield StreamEvent(delta=salvaged)
                            finish_reason = "stop"
                            break
                        err = data["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        code = str(err.get("code", "") or err.get("type", "")) if isinstance(err, dict) else ""
                        raise ProviderError(
                            f"{provider_name} stream error: {msg[:200]}",
                            provider=provider_name,
                            transient=("rate" in msg.lower() or "429" in code or "overload" in msg.lower() or "capacity" in msg.lower()),
                        )
                    if data.get("usage"):
                        usage = data["usage"] or usage
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            text_parts.append(piece)
                            yield StreamEvent(delta=piece)
                        for tc in delta.get("tool_calls") or []:
                            idx = int((tc or {}).get("index") or 0)
                            slot = calls.setdefault(idx, {"name": "", "arguments": ""})
                            fn = (tc or {}).get("function") or {}
                            if fn.get("name"):
                                slot["name"] += str(fn["name"])
                            if fn.get("arguments"):
                                slot["arguments"] += str(fn["arguments"])
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"{provider_name} timeout ({timeout}s)", provider=provider_name, transient=True
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"{provider_name} connection error: {exc}", provider=provider_name, transient=True
        ) from exc

    yield StreamEvent(
        final=ProviderResponse(
            text="".join(text_parts),
            model=model,
            provider=provider_name,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            truncated=was_cut_off(finish_reason),
            tool_calls=[c for _i, c in sorted(calls.items()) if c["name"]],
        )
    )
