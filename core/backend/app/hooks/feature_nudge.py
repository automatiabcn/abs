# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A quiet word when there is a better tool for the job.

The server ships more tools than anyone reads the list of, so most people find
one that works and never discover the one that works better. These nudges are
appended to a tool's own answer when the request looks like a job another tool
was built for — never more than one per feature per ten minutes, because a hint
that arrives every time is not a hint, it is noise.

Every tool named here is a tool this server actually exposes. A nudge that
points at something the customer does not have is worse than no nudge at all.
"""

from __future__ import annotations

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "feature_nudge_rate.json"
_WINDOW_SEC = 600  # ten minutes per feature


def _nudge_factory(rate: dict) -> tuple:
    def _allow(key: str) -> bool:
        return allow_once(rate, key, _WINDOW_SEC)

    def _persist() -> None:
        persist_rate(_RATE_FILE, rate)

    return _allow, _persist


# =============================================================================
# Command-line nudges
# =============================================================================


@safe_hook("feature_nudge_bash")
def maybe_feature_nudge_bash(cmd: str) -> str:
    if not cmd or len(cmd) < 10:
        return ""
    if "ask " not in cmd and 'ask "' not in cmd:
        return ""
    cmd_l = cmd.lower()

    rate = load_rate(_RATE_FILE)
    _allow, _persist = _nudge_factory(rate)

    # Writing code — one model writes, another checks, a third fixes.
    if "qual-code" not in cmd_l and "qual " not in cmd_l:
        kw = (
            "write a function",
            "write function",
            "implement",
            "python function",
            "javascript function",
            "react component",
            "api endpoint",
            "write code",
        )
        if any(k in cmd_l for k in kw) and "ask" in cmd_l:
            if _allow("qual-code"):
                _persist()
                return (
                    "Tip (qual-code): for code, mcp__abs__qual_code runs a "
                    "write → check → fix pipeline instead of trusting one "
                    "model's first draft."
                )

    # Comparing options — one model's opinion is not a comparison.
    if "race" not in cmd_l and "mcp__abs__race" not in cmd_l:
        kw = (
            "compare ",
            " vs ",
            "alternatives",
            "research",
            "multiple models",
            "which is better",
        )
        if any(k in cmd_l for k in kw):
            if _allow("race"):
                _persist()
                return (
                    "Tip (race): mcp__abs__race asks three models at once and "
                    "lets you pick. You are asking one."
                )

    # Documentation.
    if "write_docs" not in cmd_l and "fs-doc" not in cmd_l:
        kw = (
            "write a readme",
            "readme",
            "documentation",
            "api doc",
            "write a report",
            "detailed report",
            "user guide",
        )
        if any(k in cmd_l for k in kw):
            if _allow("docs"):
                _persist()
                return (
                    "Tip (docs): mcp__abs__write_docs drafts and proofreads in "
                    "one pass."
                )

    # Looking over a whole project.
    if all(p not in cmd_l for p in ("fs-scan", "fs-plan", "fs-exec")):
        kw = (
            "scan project",
            "project analysis",
            "what is missing",
            "gaps in",
            "project completion",
            "finish the project",
        )
        if any(k in cmd_l for k in kw):
            if _allow("fs-scan"):
                _persist()
                return (
                    "Tip (project scan): mcp__abs__fullstack_scan reads the "
                    "whole project and tells you what is missing."
                )

    # Something you already have an answer to, somewhere.
    if "rag" not in cmd_l and "mcp__abs__rag" not in cmd_l:
        kw = (
            "have we done this",
            "did we already",
            "similar pattern",
            "in our own",
            "from our docs",
            "previous project",
        )
        if any(k in cmd_l for k in kw):
            if _allow("rag"):
                _persist()
                return (
                    "Tip (RAG): mcp__abs__rag_query searches your own "
                    "documents and cites what it finds."
                )

    # Checking code rather than writing it.
    if "auto_verify" not in cmd_l and "write_tests" not in cmd_l:
        kw = (
            "write tests",
            "unit test",
            "verify code",
            "check this code",
            "security check",
            "review this code",
        )
        if any(k in cmd_l for k in kw):
            if _allow("auto_verify"):
                _persist()
                return (
                    "Tip (verify): mcp__abs__auto_verify_code and "
                    "mcp__abs__write_tests check the code three ways in "
                    "parallel."
                )

    # A yes/no that does not need a large model.
    if "granite" not in cmd_l and "verify" not in cmd_l:
        kw = ("yes or no", "pass fail", "is this correct", "true or false")
        if any(k in cmd_l for k in kw):
            if _allow("granite-fast"):
                _persist()
                return (
                    "Tip: mcp__abs__ask_granite_fast answers yes/no questions "
                    "in under two seconds."
                )

    # Writing in a language other than English.
    if "aya" not in cmd_l and "qual-tr" not in cmd_l:
        kw = (
            "grammar",
            "proofread",
            "spelling",
            "translate",
            "in turkish",
            "in spanish",
            "in german",
        )
        if any(k in cmd_l for k in kw):
            if _allow("aya"):
                _persist()
                return (
                    "Tip (languages): mcp__abs__ask_cohere_aya is the "
                    "multilingual model — better than the default outside "
                    "English."
                )

    # Images.
    if "gemini_image" not in cmd_l and "llava" not in cmd_l:
        kw = (
            "read this image",
            "image analysis",
            "read the chart",
            "mockup",
            "describe the screenshot",
        )
        if any(k in cmd_l for k in kw):
            if _allow("gemini_image"):
                _persist()
                return "Tip (images): mcp__abs__gemini_image can read pictures."

    # Output you intend to parse.
    if "gemini_structured" not in cmd_l:
        kw = ("json schema", "structured output", "extract a table", "as json")
        if any(k in cmd_l for k in kw):
            if _allow("gemini_structured"):
                _persist()
                return (
                    "Tip (structured output): mcp__abs__gemini_structured "
                    "guarantees the shape, so you do not have to parse hope."
                )

    # Hard reasoning.
    if "phi4" not in cmd_l:
        kw = ("hard maths", "math proof", "reasoning problem", "logic puzzle")
        if any(k in cmd_l for k in kw):
            if _allow("phi4"):
                _persist()
                return (
                    "Tip (reasoning): mcp__abs__ask_phi4 is the model to "
                    "reach for when the answer has to be worked out."
                )

    # Code completion.
    if "starcoder" not in cmd_l:
        kw = ("fill in the middle", "fim complet", "code completion", "autocomplete")
        if any(k in cmd_l for k in kw):
            if _allow("starcoder"):
                _persist()
                return (
                    "Tip: mcp__abs__ask_starcoder is built for completing "
                    "code, and it is fast."
                )

    # Very large inputs.
    if "scout" not in cmd_l and "longcontext" not in cmd_l:
        kw = (
            "128k",
            "200k",
            "262k",
            "long context",
            "very large file",
            "whole codebase",
        )
        if any(k in cmd_l for k in kw):
            if _allow("longcontext"):
                _persist()
                return (
                    "Tip (long context): mcp__abs__ask_longcontext and "
                    "mcp__abs__ask_scout take far more text than the default."
                )

    # Small, throwaway work.
    if "gptoss20" not in cmd_l and "ask_groq_fast" not in cmd_l:
        kw = ("very fast", "ultra fast", "simple task", "trivial task")
        if any(k in cmd_l for k in kw):
            if _allow("gptoss20"):
                _persist()
                return (
                    "Tip: mcp__abs__ask_groq_fast answers small questions in "
                    "under a second."
                )

    # Decisions you cannot take back.
    if "race" not in cmd_l:
        kw = (
            "critical decision",
            "production deploy",
            "architecture decision",
            "before we commit",
        )
        if any(k in cmd_l for k in kw):
            if _allow("race-critical"):
                _persist()
                return (
                    "Tip: for a decision you cannot undo, mcp__abs__race and "
                    "mcp__abs__ask_disagree give you three views and a measure "
                    "of how much they agree."
                )

    return ""


# =============================================================================
# Nudges on a single-model call that a pipeline would do better
# =============================================================================

_MCP_NUDGE_TARGETS = {
    # tool name → (rate-limit key, what to say)
    "ask_gptoss": (
        "mcp_qual_code",
        "Tip: you are writing code with one model. mcp__abs__race_code asks "
        "three and lets you pick; mcp__abs__qual_code writes, checks and then "
        "fixes.",
    ),
    "ask_kimi": (
        "mcp_qual_code",
        "Tip: you are writing code with one model. mcp__abs__race_code or "
        "mcp__abs__qual_code will do better.",
    ),
    "ask_qwen32b": (
        "mcp_qual_tr",
        "Tip: for prose, mcp__abs__qual_tr drafts, checks and polishes, and "
        "mcp__abs__race_tr gives you two drafts to choose between.",
    ),
    "ask_gemini": (
        "mcp_qual_tr",
        "Tip: one model, one draft. mcp__abs__qual_tr and mcp__abs__race_tr "
        "both do better on text that matters.",
    ),
    "ask_gemini_pro": (
        "mcp_qual_analysis",
        "Tip: for deep analysis, mcp__abs__qual_analysis takes three angles "
        "and synthesises them.",
    ),
    "ask_cf": (
        "mcp_fullstack",
        "Tip: mcp__abs__fullstack picks the model for the layer you are "
        "working in and checks its own output.",
    ),
    "ask_cf_gptoss": (
        "mcp_qual_analysis",
        "Tip: for a question this size, mcp__abs__qual_analysis or "
        "mcp__abs__race will hold up better than a single pass.",
    ),
    "ask_scout": (
        "mcp_code_review",
        "Tip: for sorting and ranking, mcp__abs__ask_rerank is more accurate; "
        "for judging code, mcp__abs__code_review.",
    ),
}


@safe_hook("feature_nudge_mcp")
def maybe_feature_nudge_mcp(tool_name: str, _tool_input: dict) -> str:
    """Nudge on a tool call that a better tool would have handled."""
    if not tool_name:
        return ""
    pair = _MCP_NUDGE_TARGETS.get(tool_name)
    if pair is None:
        return ""
    key, text = pair

    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, key, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)
    return text
