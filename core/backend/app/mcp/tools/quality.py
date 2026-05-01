"""Batch A — 6 quality tool (judge, write_tests, write_docs, code_review, ask_disagree, score_patch).

Not: qual_human / qual_code_human / humanize_score / auto_verify_code / auto_verify_turkish
tool'ları 006'da `app/mcp/tools/pipelines.py` içinde zaten kayıtlı; burada **yalnız** yeni 6 tool var.
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
    """SENIOR JUDGE — diff AST + LLM birleşik skoru. %60 fingerprint + %40 LLM."""
    await tracker.bump("judge_patch")
    result = await _judge_diff(unified_diff, file_path or None)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("write_tests")
async def write_tests(function_signatures: str) -> str:
    """Fonksiyon imzaları için pytest unit test üret. Happy + edge + error."""
    await tracker.bump("write_tests")
    prompt = (
        "Bu fonksiyon(lar) için pytest test yaz. Happy path + edge + error:\n\n"
        + function_signatures
    )
    try:
        provider = get_provider("cloudflare")
        resp = await provider.call(
            prompt, model="@cf/qwen/qwen2.5-coder-32b-instruct", max_tokens=2000
        )
        return resp.text or "[HATA] write_tests: empty"
    except ProviderError as exc:
        return f"[HATA] write_tests: {exc.message}"


@mcp_server.tool()
@with_hooks("write_docs")
async def write_docs(module_info: str) -> str:
    """Modül / fonksiyon için Türkçe API dokümantasyonu (markdown)."""
    await tracker.bump("write_docs")
    prompt = (
        "Bu modül için Türkçe API dokümantasyonu yaz "
        "(markdown, parametreler, örnek request/response):\n\n"
        + module_info
    )
    try:
        provider = get_provider("groq")
        resp = await provider.call(prompt, model="qwen/qwen3-32b", max_tokens=2000)
        return resp.text or "[HATA] write_docs: empty"
    except ProviderError as exc:
        return f"[HATA] write_docs: {exc.message}"


@mcp_server.tool()
@with_hooks("code_review")
async def code_review(code: str, tier: str = "auto") -> str:
    """Code review — tier auto (quick <50 sat, standard 50-200, exhaustive 200+)."""
    await tracker.bump("code_review")
    if tier == "auto":
        lines = code.count("\n")
        tier = "quick" if lines < 50 else ("exhaustive" if lines > 200 else "standard")
    instructions = {
        "quick": "güvenlik + kritik buglar",
        "standard": "güvenlik + performans + okunabilirlik",
        "exhaustive": "güvenlik + performans + okunabilirlik + stil + edge case",
    }
    focus = instructions.get(tier, instructions["quick"])
    prompt = f"Bu kodu review et, tier={tier} ({focus}). Sorunları ve önerileri listele:\n\n{code[:6000]}"
    try:
        provider = get_provider("groq")
        resp = await provider.call(prompt, model="openai/gpt-oss-120b", max_tokens=2000)
        return resp.text or "[HATA] code_review: empty"
    except ProviderError as exc:
        return f"[HATA] code_review: {exc.message}"


@mcp_server.tool()
@with_hooks("ask_disagree")
async def ask_disagree(prompt: str) -> str:
    """3 provider paralel çağrı + cosine/jaccard similarity + consensus skoru."""
    await tracker.bump("ask_disagree")
    result = await _ask_disagree_impl(prompt)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("score_patch_quality")
async def score_patch_quality(unified_diff: str) -> str:
    """Patch'e 0-10 minimalism + hunk konsantrasyon skoru ver."""
    await tracker.bump("score_patch_quality")
    r = _score_patch(unified_diff)
    return (
        f"Skor: {r['score']}/10 | hunks: {r['hunk_count']} | "
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
