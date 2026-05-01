"""13 pipeline MCP tool wrapper — qual/race/humanize/verify."""

from __future__ import annotations

import json
from typing import List

from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.pipelines.humanize.qual_code_human import QualCodeHumanPipeline
from app.pipelines.humanize.qual_human import QualHumanPipeline
from app.pipelines.humanize.scorer import humanize_score_text
from app.pipelines.quality.analysis import QualAnalysisPipeline
from app.pipelines.quality.code import QualCodePipeline
from app.pipelines.quality.translate import QualTranslatePipeline
from app.pipelines.quality.turkish import QualTrPipeline
from app.pipelines.race.code import RaceCodePipeline
from app.pipelines.race.general import RaceGeneralPipeline
from app.pipelines.race.local import RaceLocalPipeline
from app.pipelines.race.turkish import RaceTrPipeline
from app.pipelines.verify.code import AutoVerifyCodePipeline
from app.pipelines.verify.turkish import AutoVerifyTurkishPipeline

REGISTERED_TOOLS: List[str] = []


def _format_meta(result) -> str:
    """Pipeline sonucunu text + meta (steps) formatında döndür."""
    body = result.final_response or ""
    meta_lines = [f"[pipeline: {result.pipeline_type} · total: {result.total_elapsed_ms}ms]"]
    for s in result.steps:
        state = "✓" if s.ok else "✗"
        meta_lines.append(f"  {state} {s.name} · {s.model} · {s.elapsed_ms}ms")
    if result.error:
        meta_lines.append(f"  ERROR: {result.error}")
    return body + "\n\n" + "\n".join(meta_lines)


def _sum_tokens(result) -> tuple[int, int]:
    """016 — Pipeline step.meta'dan toplam tokens_in/out cikar."""
    total_in = 0
    total_out = 0
    for s in result.steps:
        if not s.meta:
            continue
        total_in += int(s.meta.get("tokens_in", 0) or 0)
        total_out += int(s.meta.get("tokens_out", 0) or 0)
    return total_in, total_out


# ─── Quality (4) ───────────────────────────────────────────────

@mcp_server.tool()
async def qual_code(prompt: str) -> str:
    """KALİTE KOD PIPELINE — Üret(kimi+gpt-oss-20b paralel) → codellama verify → gpt-oss-120b fix."""
    res = await QualCodePipeline().run(prompt)
    ti, to = _sum_tokens(res)
    await tracker.bump("qual_code", tokens_in=ti, tokens_out=to)
    return _format_meta(res)


@mcp_server.tool()
async def qual_tr(prompt: str) -> str:
    """KALİTE TÜRKÇE PIPELINE — Üret(qwen32b+gemini paralel) → aya review → kimi2 polish."""
    res = await QualTrPipeline().run(prompt)
    ti, to = _sum_tokens(res)
    await tracker.bump("qual_tr", tokens_in=ti, tokens_out=to)
    return _format_meta(res)


@mcp_server.tool()
async def qual_analysis(prompt: str) -> str:
    """KALİTE ANALİZ PIPELINE — 3 perspektif (gptoss + kimi2 + gemini-pro) → sentez."""
    res = await QualAnalysisPipeline().run(prompt)
    ti, to = _sum_tokens(res)
    await tracker.bump("qual_analysis", tokens_in=ti, tokens_out=to)
    return _format_meta(res)


@mcp_server.tool()
async def qual_translate(prompt: str) -> str:
    """KALİTE ÇEVİRİ PIPELINE — çevir → geri-çevir → karşılaştır → refine."""
    res = await QualTranslatePipeline().run(prompt)
    ti, to = _sum_tokens(res)
    await tracker.bump("qual_translate", tokens_in=ti, tokens_out=to)
    return _format_meta(res)


# ─── Race (4) ──────────────────────────────────────────────────

@mcp_server.tool()
async def race(prompt: str) -> str:
    """RACE — gpt-oss-120b vs kimi vs kimi2 paralel, ilk başarılı kazanır."""
    await tracker.bump("race")
    return _format_meta(await RaceGeneralPipeline().run(prompt))


@mcp_server.tool()
async def race_code(prompt: str) -> str:
    """RACE CODE — CF Kimi K2.5 vs Groq GPT-OSS 120B, ilk başarılı."""
    await tracker.bump("race_code")
    return _format_meta(await RaceCodePipeline().run(prompt))


@mcp_server.tool()
async def race_tr(prompt: str) -> str:
    """RACE TR — Qwen32B vs Gemini 2.5 Flash, ilk başarılı."""
    await tracker.bump("race_tr")
    return _format_meta(await RaceTrPipeline().run(prompt))


@mcp_server.tool()
async def race_local(prompt: str) -> str:
    """RACE LOCAL — Ollama phi4 vs gemma2. ABS_OLLAMA_URL gerekli."""
    await tracker.bump("race_local")
    return _format_meta(await RaceLocalPipeline().run(prompt))


# ─── Humanize (3) ──────────────────────────────────────────────

@mcp_server.tool()
async def qual_human(prompt: str) -> str:
    """QUAL + HUMANIZE — qual-tr çıktısını AI-detector'dan düşük puan alacak şekilde dönüştürür."""
    await tracker.bump("qual_human")
    return _format_meta(await QualHumanPipeline().run(prompt))


@mcp_server.tool()
async def qual_code_human(prompt: str) -> str:
    """QUAL CODE + HUMANIZE — qual-code çıktısını AI-yorumları kaldırarak yeniden yazar."""
    await tracker.bump("qual_code_human")
    return _format_meta(await QualCodeHumanPipeline().run(prompt))


@mcp_server.tool()
async def humanize_score(text: str) -> str:
    """Input metninin 'AI-written' heuristik skoru (0=insani, 1=AI). JSON döner."""
    await tracker.bump("humanize_score")
    score = humanize_score_text(text)
    return json.dumps(
        {
            "score": score.score,
            "matches": score.matches,
            "length": score.length,
            "sentence_count": score.sentence_count,
        },
        ensure_ascii=False,
    )


# ─── Auto-Verify (2) ───────────────────────────────────────────

@mcp_server.tool()
async def auto_verify_code(code: str) -> str:
    """PC GPU paralel kod doğrulama — granite-2b security + codellama test + deepseek lint."""
    await tracker.bump("auto_verify_code")
    return _format_meta(await AutoVerifyCodePipeline().run(code))


@mcp_server.tool()
async def auto_verify_turkish(text: str) -> str:
    """Türkçe metin kalite kontrolü — aya-8b ile gramer/stil."""
    await tracker.bump("auto_verify_turkish")
    return _format_meta(await AutoVerifyTurkishPipeline().run(text))


REGISTERED_TOOLS.extend(
    [
        "qual_code",
        "qual_tr",
        "qual_analysis",
        "qual_translate",
        "race",
        "race_code",
        "race_tr",
        "race_local",
        "qual_human",
        "qual_code_human",
        "humanize_score",
        "auto_verify_code",
        "auto_verify_turkish",
    ]
)
