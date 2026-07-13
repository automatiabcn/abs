# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""NL → JSON workflow synthesiser.

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

REQUIRED SHAPE (match field names EXACTLY — validator is strict):

  {
    "id": "<slug-id>",
    "name": "<short title>",
    "description": "<one-line summary>",
    "trigger": {"id": "trigger-1", "kind": "manual", "description": "..."},
    "nodes": [
      {"id": "<node-id>", "kind": "llm_call|api_request|conditional|loop|hitl",
       "name": "<human-readable step name>",
       "config": {"prompt_template": "...", "tool_name": "abs.<tool>"}}
    ],
    "edges": [{"source": "<node-id>", "target": "<node-id>"}]
  }

RULES:
  1. Respond with EXACTLY ONE JSON object. No prose. No markdown.
  2. `trigger` is REQUIRED — kind must be one of: manual, webhook, cron, event.
  3. Every node MUST have: id, kind, name (kind from allowed enum).
  4. Edges use `source`/`target` keys — NOT `from`/`to`.
  5. `nodes` and `edges` must be non-empty.
  6. Pick the smallest set of nodes that satisfies the intent — do not
     invent steps the user did not ask for.
  7. If the intent maps to multiple integrations (e.g. Slack + Linear),
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
        examples.append(
            {"intent": tmpl.title_en, "workflow": tmpl.workflow.model_dump(mode="json")}
        )
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
_SLUG_FALLBACK = re.compile(r"[^a-z0-9-]+")


def _slugify(text: str, fallback: str = "workflow") -> str:
    s = _SLUG_FALLBACK.sub("-", (text or "").lower()).strip("-")
    return s[:48] if s else fallback


def _normalize_llm_workflow(data: Any) -> Any:
    """Best-effort fix for common LLM schema drift before strict validation."""
    if not isinstance(data, dict):
        return data
    if "trigger" not in data or not isinstance(data.get("trigger"), dict):
        data["trigger"] = {
            "id": "trigger-1",
            "kind": "manual",
            "description": "auto-added",
        }
    else:
        t = data["trigger"]
        t.setdefault("id", "trigger-1")
        t.setdefault("kind", "manual")
        if t.get("kind") not in ("manual", "webhook", "cron", "event"):
            t["kind"] = "manual"
    data.setdefault("id", _slugify(data.get("name", "")))
    data.setdefault("name", data.get("id", "Synthesized Workflow"))
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                continue
            n.setdefault("id", f"n{i + 1}")
            n.setdefault("name", n.get("id", f"Step {i + 1}").replace("-", " ").title())
            kind = n.get("kind")
            if kind not in ("llm_call", "api_request", "conditional", "loop", "hitl"):
                tool = n.get("tool") or n.get("config", {}).get("tool_name") or ""
                if "request" in tool or "http" in tool or "api" in tool:
                    n["kind"] = "api_request"
                elif tool.startswith("abs.hitl") or "approval" in tool:
                    n["kind"] = "hitl"
                else:
                    n["kind"] = "llm_call"
            if "tool" in n and "config" not in n:
                n["config"] = {"tool_name": n["tool"]}
            elif "tool" in n and isinstance(n.get("config"), dict):
                n["config"].setdefault("tool_name", n["tool"])
            cfg = n.get("config")
            if isinstance(cfg, dict):
                if "prompt_template" in cfg and "prompt" not in cfg:
                    cfg["prompt"] = cfg.pop("prompt_template")
                _allowed_cfg = {
                    "model",
                    "prompt",
                    "method",
                    "url",
                    "tool_name",
                    "tool_args",
                    "condition_expr",
                    "approval_role",
                    "script",
                    "output_template",
                }
                for k in list(cfg.keys()):
                    if k not in _allowed_cfg:
                        cfg.pop(k, None)
            for k in list(n.keys()):
                if k not in {"id", "kind", "name", "config", "retry_max", "timeout_s"}:
                    n.pop(k, None)
    edges = data.get("edges")
    if isinstance(edges, list):
        for e in edges:
            if not isinstance(e, dict):
                continue
            if "source" not in e and "from" in e:
                e["source"] = e.pop("from")
            if "target" not in e and "to" in e:
                e["target"] = e.pop("to")
    return data


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
            data = _normalize_llm_workflow(data)
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
