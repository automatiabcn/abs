# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Hook dispatcher — 5 modülü sıralı çağırır, Claude Code PreToolUse spec'i üretir.

Sıra (SERVER guard_logic.py'den):
  1. freeze       — (MVP: placeholder — 008'de sertleşir)
  2. investigate  — (MVP: placeholder)
  3. content-enrich (enrichment.maybe_enrichment_notice)
  4. rag-inject    (rag_inject.maybe_rag_inject — STUB)
  5. plan-first    (plan_first.maybe_plan_first_nudge)
  6. feature-nudge (feature_nudge.maybe_feature_nudge_bash + _mcp)
  7. delegate-nudge(delegate_nudge.maybe_delegate_nudge)

Her hook `safe_hook` decorator'ı ile — bir tanesi çökse diğerleri devam eder.
Çıktı: `{"additional_context": str, "deny_reason": str | None}` dict.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.config import settings

from . import delegate_nudge, enrichment, feature_nudge, plan_first, rag_inject

logger = logging.getLogger(__name__)


def _is_mcp_tool(tool_name: str) -> bool:
    return tool_name.startswith("mcp__") or tool_name.startswith("ask_") or tool_name in (
        "qual_code", "qual_tr", "qual_analysis", "qual_translate",
        "race", "race_code", "race_tr", "race_local",
        "qual_human", "qual_code_human", "humanize_score",
        "auto_verify_code", "auto_verify_turkish",
        "ask_haiku", "ask_sonnet", "ask_opus",
        "system_status",
    )


def _strip_prefix(tool_name: str) -> str:
    """mcp__abs__ask_gptoss → ask_gptoss."""
    if tool_name.startswith("mcp__abs__"):
        return tool_name[len("mcp__abs__"):]
    return tool_name


def dispatch_hooks(tool_name: str, tool_input: Dict[str, Any] | None) -> Dict[str, Any]:
    """Tüm hook'ları çalıştır, ek context / deny reason döndür."""
    if not settings.hooks_enabled:
        return {"additional_context": "", "deny_reason": None}

    tool_input = tool_input or {}
    ctx_parts: List[str] = []
    deny: str | None = None

    def _safe(name: str, fn, *args):
        """Tek hook çağrısı için son savunma — stub'lar safe_hook'suz olabilir."""
        try:
            return fn(*args) or ""
        except Exception as exc:
            logger.info("hook %s raised: %s", name, exc)
            return ""

    # 3. enrichment (Write gate)
    msg = _safe("enrichment", enrichment.maybe_enrichment_notice, tool_name, tool_input)
    if msg:
        ctx_parts.append(msg)

    # 4. rag_inject (Bash/Write/Edit — STUB)
    msg = _safe("rag_inject", rag_inject.maybe_rag_inject, tool_name, tool_input)
    if msg:
        ctx_parts.append(msg)

    # 5. plan-first
    msg = _safe("plan_first", plan_first.maybe_plan_first_nudge, tool_name, tool_input)
    if msg:
        ctx_parts.append(msg)

    # 6. feature-nudge
    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        msg = _safe("feature_nudge_bash", feature_nudge.maybe_feature_nudge_bash, cmd)
        if msg:
            ctx_parts.append(msg)
    elif _is_mcp_tool(tool_name):
        stripped = _strip_prefix(tool_name)
        msg = _safe("feature_nudge_mcp", feature_nudge.maybe_feature_nudge_mcp, stripped, tool_input)
        if msg:
            ctx_parts.append(msg)

    # 7. delegate-nudge
    msg = _safe("delegate_nudge", delegate_nudge.maybe_delegate_nudge, tool_name, tool_input)
    if msg:
        ctx_parts.append(msg)

    return {
        "additional_context": "\n\n".join(ctx_parts),
        "deny_reason": deny,
    }


def to_claude_code_hook_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """Claude Code PreToolUse hook JSON spec'ine dönüştür."""
    if result.get("deny_reason"):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": result["deny_reason"],
            }
        }
    ctx = result.get("additional_context", "")
    if not ctx:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": ctx,
        }
    }
