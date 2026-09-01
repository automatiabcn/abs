# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""One step of the editor agent's loop, as a stream of events.

The editor drives the loop; this is what happens between two of its tool
calls: assemble the prompt for where the run stands, ask the cascade, and
read the reply as a tool call or as the answer. Events, one JSON object per
SSE frame:

    meta        {step, mode, lang, intent, used_files, chain, max_steps}
    provider    {name, streams}            — a leg starts
    leg_failed  {name, detail, transient}  — a leg failed before its first word
    delta       {text}                     — a piece of the answer (prose only)
    action      {name, args, where, level, needs_approval, error?}
                                           — the model wants a tool run
    replace     {text}                     — the answer was regenerated
    final       {text, unverified, lang_drift?, continued, provider, …}
    error       {error, detail, partial?}

Four guards live here because they must see the whole reply, and the
transcript of 2026-09-01 shows each one earning its place:

* the first ~240 characters are held back until it is clear whether they
  are a tool call (JSON, never shown) or prose (shown as it arrives);
* a leaked reasoning channel ("We need to request the file list.") is
  stripped from that prefix before the developer sees it;
* an answer cut off by the token limit is continued, twice at most, rather
  than delivered as a blank ("The answer was cut off");
* an answer that left the developer's language is regenerated once with
  the language named, and references to files the project does not have
  are marked unverified rather than shown as fact.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.chat import language as lang
from app.chat.cleanup import strip_leaked_reasoning, verify_references
from app.editor_agent import tools as toolbox
from app.editor_agent.context import (
    INITIAL_FILES_MAX,
    EditorState,
    StepRecord,
    Todo,
    build_prompt,
    detect_intent,
    must_answer,
)
from app.editor_agent.protocol import REPAIR_NOTE, looks_like_json_start, parse_reply
from app.providers.chain import resolve_chain

logger = logging.getLogger(__name__)

PREFIX_HOLD = 240
MAX_CONTINUATIONS = 2
DEFAULT_MAX_TOKENS = 3000
# A tool-using run is a long task, not a keystroke: when every provider is
# rate-limited the right move is to wait and go on, not to fail the turn.
# One free key on Groq answers a 429 with a 10-25s Retry-After and is fine
# afterwards (live 09-01, nine steps in a row).
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_WAIT_S = 25.0


def _rate_limited(detail: str) -> bool:
    t = (detail or "").lower()
    return "rate limit" in t or "429" in t or "recover shortly" in t or "too many requests" in t


def _too_large(detail: str) -> bool:
    t = (detail or "").lower()
    return "too large" in t or "413" in t or "context length" in t or "maximum context" in t


def _model_pins() -> Dict[str, str]:
    """The Composer's per-provider model pins (the strongest free model each
    provider serves), so a run is not answered by a provider's small default."""
    try:
        from app.composer.runtime import _COMPOSER_MODELS

        return dict(_COMPOSER_MODELS)
    except Exception:  # noqa: BLE001
        return {}


_MODELS = _model_pins()
# Cloudflare's default is a chat model; for a tool-using run the strongest
# open model it serves is the one to ask for.
_MODELS.setdefault("cloudflare", "@cf/openai/gpt-oss-120b")


def _native_tools(mode: str) -> List[Dict[str, Any]]:
    """The catalogue in the OpenAI function-calling shape. Providers that
    support it (Groq's gpt-oss does, and insists on it — it emits a native
    call whether or not one was offered) get real tool calls back; the
    others ignore the field and the JSON-in-text protocol still works."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in toolbox.catalogue(mode)
    ]


def _from_native(resp: Any):
    """A Parsed tool call from a response's native tool_calls, or None."""
    import json as _json

    from app.editor_agent.protocol import Parsed

    for tc in list(getattr(resp, "tool_calls", []) or [])[:1]:
        name = str(tc.get("name") or "").strip()
        raw = tc.get("arguments")
        try:
            args = _json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw if isinstance(raw, dict) else {})
        except ValueError:
            args = {}
        if name:
            return Parsed("tool", name=name, args=args if isinstance(args, dict) else {})
    return None


class StepRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=60_000)
    mode: str = "agent"
    history: str = Field(default="", max_length=40_000)
    prefer: str = ""
    workspace_root: str = ""
    client_id: str = ""
    lang: str = ""
    editor: Optional[EditorState] = None
    plan: List[Todo] = Field(default_factory=list, max_length=60)
    steps: List[StepRecord] = Field(default_factory=list, max_length=60)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=64, le=8000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


def _language(body: StepRequest) -> str:
    if body.lang in lang.NAMES:
        return body.lang
    code = lang.detect(body.message)
    if code:
        return code
    # The developer's earlier lines, not the assistant's — the drift we are
    # guarding against is exactly the assistant's language leaking in.
    mine = "\n".join(
        l[len("Developer:"):] for l in body.history.splitlines() if l.startswith("Developer:")
    )
    return lang.detect(mine)


def _prepare(body: StepRequest, tenant: str, user: str, compact: bool = False) -> Dict[str, Any]:
    """Everything that reads the disk, in one place, off the event loop.
    `compact`: the provider refused the size once; everything optional shrinks."""
    from app.config import settings

    chain = resolve_chain(body.prefer, tenant, user)
    if "error" in chain:
        return chain
    if not body.prefer.strip():
        # A tool-using run is the hardest thing we ask a model to do: the
        # order is the Composer's (strongest first), not the cost-first chat
        # default. A named provider still comes first.
        from app.cascade.routing import DEEP, chain_for

        ordered = chain_for(DEEP, chain["active"]) or list(chain["active"])
        chain = {**chain, "primary": ordered[0], "fallbacks": tuple(ordered[1:])}
    root = ""
    listing: List[str] = []
    files: List[Tuple[str, str]] = []
    rules = rules_from = ""
    try:
        from app.chat.context import project_rules
        from app.composer.runtime import relevant_files, workspace_files
        from app.codegraph.graph import tenant_key as _key_for
        from app.workspace.current import current_workspace

        root = (
            current_workspace(
                tenant, user or "", client_id=body.client_id, explicit_root=body.workspace_root
            )
            or ""
        )
        if root:
            listing = workspace_files(root)
            rules, rules_from = project_rules(root)
            if not body.steps:
                files = relevant_files(
                    root, body.message, listing, graph_key=_key_for(tenant, root)
                )
    except Exception as exc:  # noqa: BLE001 — context is an aid, not a gate
        logger.warning("editor_agent_context_failed err=%s", exc)
    code = _language(body)
    intent = detect_intent(body.message)
    max_steps = int(getattr(settings, "editor_agent_max_steps", 12))
    answer_now = must_answer(body.steps, max_steps)
    prompt = build_prompt(
        message=body.message,
        mode=body.mode if body.mode in toolbox.MODES else "ask",
        lang_code=code,
        intent=intent,
        project_name=os.path.basename(root) if root else "",
        rules=rules,
        rules_from=rules_from,
        listing=listing,
        files=files,
        history=body.history,
        editor=body.editor,
        plan=body.plan,
        steps=body.steps,
        max_steps=max_steps,
        native_tools=not answer_now,
        compact=compact,
    )
    return {
        **chain,
        "root": root,
        "listing": listing,
        "used_files": [rel for rel, _ in files[:INITIAL_FILES_MAX]],
        "lang": code,
        "intent": intent,
        "prompt": prompt,
        "tools": None if answer_now else _native_tools(body.mode if body.mode in toolbox.MODES else "ask"),
        "must_answer": answer_now,
        "compact": compact,
    }


async def _ask_once(
    prompt: str, prepared: Dict[str, Any], max_tokens: int, temperature: float
) -> Any:
    from app.cascade.orchestrator import call_with_cascade

    return await call_with_cascade(
        prompt,
        primary=prepared["primary"],
        fallbacks=prepared["fallbacks"],
        models=_MODELS,
        max_tokens=max_tokens,
        temperature=temperature,
        use_cache=False,
        tenant_id=prepared["tenant"],
        user_subject=prepared["user"],
        reasoning_effort="low",
        tools=prepared.get("tools") or None,
    )


def _cost(resp: Any) -> Dict[str, Any]:
    tokens_in = int(getattr(resp, "tokens_in", 0) or 0)
    tokens_out = int(getattr(resp, "tokens_out", 0) or 0)
    usd: Optional[float] = None
    try:
        from app.chat.cost import estimate_call_cost_usd

        usd = estimate_call_cost_usd(
            provider=getattr(resp, "provider", None) or None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=getattr(resp, "model", None),
        ).get("usd")
    except Exception:  # noqa: BLE001
        usd = None
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "usd": usd}


def _action_event(parsed, mode: str) -> Dict[str, Any]:
    tool = toolbox.get(parsed.name)
    if tool is None or not toolbox.allowed(parsed.name, mode):
        names = ", ".join(t["name"] for t in toolbox.catalogue(mode))
        return {
            "type": "action",
            "name": parsed.name,
            "args": parsed.args,
            "where": "none",
            "level": "read",
            "needs_approval": False,
            "error": f"System: there is no tool called '{parsed.name}' in this mode. Use one of: {names}.",
        }
    try:
        args = toolbox.validate_args(tool, parsed.args)
    except ValueError as exc:
        return {
            "type": "action",
            "name": parsed.name,
            "args": parsed.args,
            "where": tool["where"],
            "level": tool["level"],
            "needs_approval": tool["level"] != "read",
            "error": f"System: tool '{parsed.name}' rejected the call: {exc}",
        }
    return {
        "type": "action",
        "name": parsed.name,
        "args": args,
        "where": tool["where"],
        "level": tool["level"],
        "needs_approval": tool["level"] != "read",
    }


async def run_step(
    body: StepRequest,
    *,
    tenant: str,
    user: str,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    from app.cascade.orchestrator import stream_with_cascade
    from app.config import settings

    prepared = await asyncio.to_thread(_prepare, body, tenant, user)
    if "error" in prepared:
        err = dict(prepared["error"])
        err["type"] = "error"
        yield err
        return
    mode = body.mode if body.mode in toolbox.MODES else "ask"
    yield {
        "type": "meta",
        "step": len(body.steps) + 1,
        "mode": mode,
        "lang": prepared["lang"],
        "intent": prepared["intent"],
        "used_files": prepared["used_files"],
        "chain": [prepared["primary"], *prepared["fallbacks"]],
        "max_steps": int(getattr(settings, "editor_agent_max_steps", 12)),
        "project": os.path.basename(prepared["root"]) if prepared["root"] else "",
    }

    started = time.perf_counter()
    state: Dict[str, Any] = {
        "buf": "",  # what the provider said, before the developer sees any of it
        "shown": "",  # what the developer has been shown
        "decided": None,  # "tool" | "prose"
        "resp": None,
    }
    calls: List[Any] = []

    async def gone() -> bool:
        return bool(is_disconnected and await is_disconnected())

    def on_delta(piece: str) -> Optional[Dict[str, Any]]:
        """Fold one piece into the buffer; return the frame to show, if any."""
        state["buf"] += piece
        buf = state["buf"]
        if state["decided"] is None:
            head = buf.lstrip()
            if head and looks_like_json_start(head):
                state["decided"] = "tool"
                return None
            if len(buf) >= PREFIX_HOLD:
                state["decided"] = "prose"
                state["shown"] = strip_leaked_reasoning(buf)
                return {"type": "delta", "text": state["shown"]}
            return None
        if state["decided"] == "prose":
            shown = state["shown"]
            new = buf[len(shown):] if buf.startswith(shown) else piece
            state["shown"] = buf if buf.startswith(shown) else shown + new
            return {"type": "delta", "text": new}
        return None

    async def one_attempt() -> AsyncIterator[Dict[str, Any]]:
        """One walk down the chain. Raises on a failure before any text."""
        async for ev in stream_with_cascade(
            prepared["prompt"],
            primary=prepared["primary"],
            fallbacks=prepared["fallbacks"],
            models=_MODELS,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            use_cache=False,
            tenant_id=prepared["tenant"],
            user_subject=prepared["user"],
            reasoning_effort="low",
            tools=prepared.get("tools") or None,
        ):
            kind = ev.get("type")
            if kind == "provider":
                yield {
                    "type": "provider",
                    "name": ev.get("name", ""),
                    "streams": bool(ev.get("streams", False)),
                }
            elif kind == "leg_failed":
                yield {
                    "type": "leg_failed",
                    "name": ev.get("name", ""),
                    "detail": ev.get("detail", ""),
                    "transient": bool(ev.get("transient", True)),
                }
            elif kind == "delta":
                frame = on_delta(str(ev.get("text") or ""))
                if frame:
                    yield frame
            elif kind == "error":
                yield {
                    "type": "error",
                    "error": "provider_failed_mid_answer",
                    "detail": ev.get("detail", ""),
                    "partial": state["buf"] if state["decided"] == "prose" else "",
                    "providers_tried": ev.get("providers_tried", []),
                }
                return
            elif kind == "done":
                state["resp"] = ev["response"]
                calls.append(ev["response"])

    attempt = 0
    shrunk = False
    while state["resp"] is None:
        attempt += 1
        failed = ""
        try:
            async for frame in one_attempt():
                if await gone():
                    return
                yield frame
                if frame.get("type") == "error":
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — report, never 500 mid-stream
            failed = str(exc)[:400]
        if state["resp"] is not None:
            break
        if not failed:
            break
        if _too_large(failed) and not shrunk and not state["buf"]:
            # The provider's window is smaller than this step (a free tier
            # after a big read_file, live 09-01). Once: the same step with
            # everything optional shrunk, before giving up.
            shrunk = True
            compact = await asyncio.to_thread(_prepare, body, tenant, user, True)
            if "error" not in compact:
                prepared = compact
                yield {"type": "waiting", "seconds": 0, "reason": "the request was too large for the provider; retrying with a smaller context", "attempt": attempt}
                continue
        if not _rate_limited(failed) or attempt > RATE_LIMIT_RETRIES or state["buf"]:
            yield {
                "type": "error",
                "error": "cascade_failed",
                "detail": failed,
                "tried": list(prepared.get("active", [])),
            }
            return
        yield {"type": "waiting", "seconds": RATE_LIMIT_WAIT_S, "reason": failed, "attempt": attempt}
        await asyncio.sleep(RATE_LIMIT_WAIT_S)
        if await gone():
            return

    resp = state["resp"]
    buf = state["buf"]
    shown = state["shown"]
    decided = state["decided"]
    if resp is None:
        yield {"type": "error", "error": "no_answer", "detail": "the provider closed without an answer"}
        return

    text = buf
    native = _from_native(resp)
    if prepared.get("must_answer") and (native is not None or looks_like_json_start(text)):
        # The tools were withheld and the model still asked for one: one more
        # call, in words, for the answer.
        try:
            again = await _ask_once(
                prepared["prompt"] + "\n\nSystem: tools are no longer available. Write the answer for the developer now, as text.",
                prepared, body.max_tokens, body.temperature,
            )
            calls.append(again)
            text = again.text or ""
            native = None
            decided = "prose"
        except Exception as exc:  # noqa: BLE001
            logger.info("editor_agent forced answer failed: %s", exc)
            text = ""
    if native is not None:
        # The model called a tool the native way: no text to parse, no
        # prefix to hold, no repair turn to spend.
        ev = _action_event(native, mode)
        ev["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        ev["provider"] = getattr(resp, "provider", "") or ""
        ev["native"] = True
        yield ev
        return
    if decided is None:
        decided = "tool" if looks_like_json_start(text) else "prose"

    # --- a tool call ---------------------------------------------------------
    if decided == "tool":
        parsed = parse_reply(text)
        if parsed.kind == "invalid":
            try:
                fix = await _ask_once(
                    prepared["prompt"] + "\n\n" + REPAIR_NOTE, prepared, body.max_tokens, body.temperature
                )
                calls.append(fix)
                text = fix.text or ""
                parsed = _from_native(fix) or parse_reply(text)
            except Exception as exc:  # noqa: BLE001
                logger.info("editor_agent repair call failed: %s", exc)
        if parsed.kind == "tool":
            ev = _action_event(parsed, mode)
            ev["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
            ev["provider"] = getattr(resp, "provider", "") or ""
            yield ev
            return
        if parsed.kind == "final":
            text = parsed.text
        else:
            # Still not readable. The developer gets the words, marked.
            text = text.strip()
        # fall through: what we have is the answer

    # --- the answer ----------------------------------------------------------
    text = strip_leaked_reasoning(text)
    if not text.strip():
        # A provider that answered with nothing (all of its budget spent on
        # reasoning, or a stream that closed early). One more try, then say so
        # — a blank bubble is the one answer the developer cannot act on.
        try:
            again = await _ask_once(prepared["prompt"], prepared, body.max_tokens, body.temperature)
            calls.append(again)
            text = strip_leaked_reasoning(again.text or "")
            parsed = _from_native(again)
            if parsed is None and looks_like_json_start(text):
                parsed = parse_reply(text)
            if parsed is not None:
                if parsed.kind == "tool":
                    ev = _action_event(parsed, mode)
                    ev["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
                    ev["provider"] = getattr(again, "provider", "") or ""
                    yield ev
                    return
        except Exception as exc:  # noqa: BLE001
            logger.info("editor_agent empty-answer retry failed: %s", exc)
        if not text.strip():
            yield {
                "type": "error",
                "error": "empty_answer",
                "detail": f"{getattr(resp, 'provider', '') or 'the provider'} answered with nothing, twice.",
                "providers_tried": list(getattr(resp, "providers_tried", []) or []),
            }
            return
        if decided == "prose":
            yield {"type": "delta", "text": text}
            shown = text
    continued = 0
    truncated = bool(getattr(resp, "truncated", False))
    while truncated and continued < MAX_CONTINUATIONS:
        try:
            more = await _ask_once(
                prepared["prompt"]
                + "\n\nYour answer so far (it was cut off by the length limit):\n"
                + text[-6000:]
                + "\n\nContinue exactly where it stopped. Do not repeat what is above; "
                "do not start over; no preamble.",
                prepared,
                body.max_tokens,
                body.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("editor_agent continuation failed: %s", exc)
            break
        calls.append(more)
        piece = strip_leaked_reasoning(more.text or "")
        if not piece.strip():
            break
        sep = "" if text.endswith(("\n", " ")) or piece.startswith(("\n", " ")) else " "
        text = text + sep + piece
        continued += 1
        truncated = bool(getattr(more, "truncated", False))
        if decided == "prose":
            yield {"type": "delta", "text": sep + piece}
            shown = text

    drift, got = lang.drifted(prepared["lang"], text)
    regenerated = False
    if drift:
        try:
            again = await _ask_once(
                prepared["prompt"]
                + f"\n\nSystem: your previous answer was written in {lang.name(got)}. The "
                f"developer writes in {lang.name(prepared['lang'])}. Write the same answer "
                f"again, entirely in {lang.name(prepared['lang'])} (code and paths unchanged).",
                prepared,
                body.max_tokens,
                body.temperature,
            )
            calls.append(again)
            candidate = strip_leaked_reasoning(again.text or "").strip()
            if candidate and not lang.drifted(prepared["lang"], candidate)[0]:
                text = candidate
                regenerated = True
        except Exception as exc:  # noqa: BLE001
            logger.info("editor_agent language regeneration failed: %s", exc)

    text, unverified = verify_references(text, prepared["listing"])
    if decided == "prose" and not regenerated and text != shown:
        # Cleanup changed something the developer already saw (a placeholder
        # line number, a stray token): the final frame carries the whole text
        # and the panel takes it as the answer.
        pass
    if regenerated:
        yield {"type": "replace", "text": text}

    tokens_in = sum(_cost(c)["tokens_in"] for c in calls)
    tokens_out = sum(_cost(c)["tokens_out"] for c in calls)
    usd_parts = [_cost(c)["usd"] for c in calls]
    usd = sum(u for u in usd_parts if isinstance(u, (int, float))) if any(
        isinstance(u, (int, float)) for u in usd_parts
    ) else None
    yield {
        "type": "final",
        "text": text,
        "unverified": unverified,
        "lang": prepared["lang"],
        "lang_drift": got if drift else "",
        "regenerated": regenerated,
        "continued": continued,
        "truncated": truncated,
        "degraded": decided == "tool",
        "provider": getattr(resp, "provider", "") or "",
        "model": getattr(resp, "model", "") or "",
        "providers_tried": list(getattr(resp, "providers_tried", []) or []),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": usd,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "used_files": prepared["used_files"],
    }
