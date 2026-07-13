# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Quality tools — judge, write_tests, write_docs, code_review, ask_disagree, score_patch.

The humanize and auto-verify tools live in `app/mcp/tools/pipelines.py`; they are
multi-step pipelines, these are single calls.
"""

from __future__ import annotations

import json
from typing import List

from app.disagreement import ask_disagree as _ask_disagree_impl
from app.judge import judge_diff as _judge_diff
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.patches import score_patch as _score_patch
from app.providers.registry import get_provider
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("judge_patch")
async def judge_patch(unified_diff: str, file_path: str = "") -> str:
    """SENIOR JUDGE — score a diff: 60% AST fingerprint, 40% model judgement."""
    await tracker.bump("judge_patch")
    result = await _judge_diff(unified_diff, file_path or None)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("write_tests")
async def write_tests(function_signatures: str) -> str:
    """Write pytest unit tests for the given signatures: happy path, edges, errors."""
    await tracker.bump("write_tests")
    prompt = (
        "Write pytest tests for the following function(s). Cover the happy path, "
        "edge cases and error cases:\n\n" + function_signatures
    )
    try:
        provider = get_provider("cloudflare")
        resp = await provider.call(
            prompt, model="@cf/qwen/qwen2.5-coder-32b-instruct", max_tokens=2000
        )
        return resp.text or "[ERROR] write_tests: empty"
    except ProviderError as exc:
        return f"[ERROR] write_tests: {exc.message}"


@mcp_server.tool()
@with_hooks("write_docs")
async def write_docs(module_info: str) -> str:
    """API documentation for a module or function, in markdown."""
    await tracker.bump("write_docs")
    prompt = (
        "Write API documentation for this module in markdown: what it does, its "
        "parameters, and an example request and response:\n\n" + module_info
    )
    try:
        provider = get_provider("groq")
        resp = await provider.call(prompt, model="qwen/qwen3-32b", max_tokens=2000)
        return resp.text or "[ERROR] write_docs: empty"
    except ProviderError as exc:
        return f"[ERROR] write_docs: {exc.message}"


@mcp_server.tool()
@with_hooks("code_review")
async def code_review(code: str, tier: str = "auto") -> str:
    """Code review. tier="auto" picks by size: quick <50 lines, standard 50-200,
    exhaustive above that."""
    await tracker.bump("code_review")
    if tier == "auto":
        lines = code.count("\n")
        tier = "quick" if lines < 50 else ("exhaustive" if lines > 200 else "standard")
    instructions = {
        "quick": "security and critical bugs",
        "standard": "security, performance, readability",
        "exhaustive": "security, performance, readability, style, edge cases",
    }
    focus = instructions.get(tier, instructions["quick"])
    prompt = (
        f"Review this code at tier={tier} ({focus}). List the problems you find "
        f"and what to do about them:\n\n{code[:6000]}"
    )
    try:
        provider = get_provider("groq")
        resp = await provider.call(prompt, model="openai/gpt-oss-120b", max_tokens=2000)
        return resp.text or "[ERROR] code_review: empty"
    except ProviderError as exc:
        return f"[ERROR] code_review: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_disagree")
async def ask_disagree(prompt: str) -> str:
    """Ask three providers in parallel and score how much they agree — a low
    consensus score is the signal that the answer is not safe to trust."""
    await tracker.bump("ask_disagree")
    result = await _ask_disagree_impl(prompt)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("score_patch_quality")
async def score_patch_quality(unified_diff: str) -> str:
    """Score a patch 0-10 on minimalism and how concentrated its hunks are."""
    await tracker.bump("score_patch_quality")
    r = _score_patch(unified_diff)
    return (
        f"Score: {r['score']}/10 | hunks: {r['hunk_count']} | "
        f"minimal_ratio: {r['minimal_ratio']} | max_hunk: {r['max_hunk_size']}\n"
        f"{r['teaching']}"
    )


REGISTERED_TOOLS.extend(
    [
        "judge_patch",
        "write_tests",
        "write_docs",
        "code_review",
        "ask_disagree",
        "score_patch_quality",
    ]
)
