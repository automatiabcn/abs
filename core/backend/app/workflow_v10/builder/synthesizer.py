# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""NL → JSON workflow synthesiser (Sprint 19 T-S03.2).

Few-shot LLM prompt that turns a free-text user intent into a JSON workflow
matching `Workflow` ontology. The actual LLM call is delegated to
`app.providers.registry.get_provider(...)` so existing observability + cerbos
gates fire automatically.

For unit tests, the LLM call is replaced with an injected `synth_fn` callable
returning a JSON string. Production passes a thin wrapper around the cascade.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .ontology import Workflow
from .templates import list_templates

SynthFn = Callable[[str], Awaitable[str]]


_FEW_SHOT_HEADER = """You are an ABS workflow architect. Given a user intent in any language,
output ONLY a JSON object that conforms to the ABS Workflow schema. No prose,
no markdown fences, no commentary before or after the JSON. Use abs.* tool
names where appropriate.

REQUIRED SHAPE (any extra keys are dropped by the validator):

  {
    "id": "<slug-id>",
    "name": "<short title>",
    "nodes": [
      {"id": "<node-id>", "tool": "abs.<tool>", "params": { ... }, "next": "<id|null>"}
    ],
    "edges": [{"from": "<id>", "to": "<id>"}]
  }

RULES:
  1. Respond with EXACTLY ONE JSON object. No prose. No markdown.
  2. Every node must reference a real abs.* tool from the examples below.
  3. `nodes` and `edges` must be non-empty.
  4. Pick the smallest set of nodes that satisfies the intent — do not
     invent steps the user did not ask for.
  5. If the intent maps to multiple integrations (e.g. Slack + Linear),
     wire them in dependency order via `edges`."""


@dataclass
class SynthesisResult:
    workflow: Workflow
    raw_json: str
    revisions: int


class SynthesisError(RuntimeError):
    """Raised when the synthesizer cannot produce a valid Workflow."""


def _few_shot_examples(limit: int = 3) -> list[dict[str, Any]]:
    """Pick a small slice of templates to ground the LLM with concrete shapes."""
    examples: list[dict[str, Any]] = []
    for tmpl in list_templates()[:limit]:
        examples.append({"intent": tmpl.title_en, "workflow": tmpl.workflow.model_dump(mode="json")})
    return examples


def build_prompt(intent: str, *, locale: str = "en") -> str:
    examples = _few_shot_examples()
    lines = [_FEW_SHOT_HEADER, "", "Examples:"]
    for ex in examples:
        lines.append(f"User intent: {ex['intent']}")
        lines.append("Workflow JSON:")
        lines.append(json.dumps(ex["workflow"], ensure_ascii=False))
        lines.append("")
    lines.append(f"User intent ({locale}): {intent}")
    lines.append("Workflow JSON:")
    return "\n".join(lines)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull the largest top-level JSON object from a free-form LLM reply."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        raise SynthesisError("LLM reply contains no JSON object")
    return m.group(0)


async def synthesize(
    intent: str,
    *,
    synth_fn: SynthFn,
    locale: str = "en",
    max_revisions: int = 3,
    revise_hint: Optional[str] = None,
) -> SynthesisResult:
    """Run synth → parse → validate, with up to `max_revisions` LLM retries."""
    prompt = build_prompt(intent, locale=locale)
    last_err: Exception | None = None
    raw = ""
    for attempt in range(max_revisions + 1):
        full_prompt = prompt
        if attempt > 0 and revise_hint:
            full_prompt = f"{prompt}\n\nRevision required: {revise_hint}"
        raw = await synth_fn(full_prompt)
        try:
            data = json.loads(extract_json(raw))
            wf = Workflow.model_validate(data)
            return SynthesisResult(workflow=wf, raw_json=raw, revisions=attempt)
        except Exception as exc:  # parse OR validation error
            last_err = exc
            revise_hint = (
                "Previous attempt failed validation: "
                f"{type(exc).__name__}: {str(exc)[:240]}"
            )
            continue
    raise SynthesisError(
        f"failed after {max_revisions + 1} attempts: {type(last_err).__name__}: {last_err}"
    )


__all__ = [
    "SynthFn",
    "SynthesisError",
    "SynthesisResult",
    "build_prompt",
    "extract_json",
    "synthesize",
]
