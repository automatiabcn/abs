"""race_code: CF Kimi K2.5 vs Groq GPT-OSS 120B — kod için."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import race_first_success
from app.providers.registry import get_provider


class RaceCodePipeline(BasePipeline):
    pipeline_type = "race-code"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        cf = get_provider("cloudflare")
        groq = get_provider("groq")

        winner = await race_first_success(
            {
                "cf-kimi": cf.call(prompt, model="@cf/moonshotai/kimi-k2.5"),
                "groq-gptoss-120b": groq.call(prompt, model="openai/gpt-oss-120b"),
            }
        )
        elapsed = int((time.monotonic() - total_start) * 1000)

        if winner is None:
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=[PipelineStep(name="race", model="-", elapsed_ms=elapsed, ok=False)],
                final_response="",
                total_elapsed_ms=elapsed,
                prompt=prompt,
                error="Kod yarışını kimse kazanmadı",
            )

        name, resp = winner
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=[
                PipelineStep(
                    name="race",
                    model=resp.model,
                    elapsed_ms=elapsed,
                    ok=True,
                    meta={"winner": name},
                )
            ],
            final_response=resp.text,
            total_elapsed_ms=elapsed,
            prompt=prompt,
        )
