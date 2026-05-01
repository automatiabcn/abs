"""race: gpt-oss-120b vs kimi (CF) vs kimi2 (CF long-ctx) — ilk başarılı kazanır."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import race_first_success
from app.providers.registry import get_provider


class RaceGeneralPipeline(BasePipeline):
    pipeline_type = "race"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        steps: list[PipelineStep] = []
        groq = get_provider("groq")
        cf = get_provider("cloudflare")

        winner = await race_first_success(
            {
                "gptoss-120b": groq.call(prompt, model="openai/gpt-oss-120b"),
                "kimi": cf.call(prompt, model="@cf/moonshotai/kimi-k2.5"),
                "kimi2": cf.call(prompt, model="@cf/moonshotai/kimi-k2.5"),
            }
        )
        elapsed = int((time.monotonic() - total_start) * 1000)

        if winner is None:
            steps.append(
                PipelineStep(name="race", model="-", elapsed_ms=elapsed, ok=False)
            )
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=elapsed,
                prompt=prompt,
                error="Hiçbir provider yarışı kazanamadı",
            )

        name, resp = winner
        steps.append(
            PipelineStep(
                name="race",
                model=resp.model,
                elapsed_ms=elapsed,
                ok=True,
                meta={"winner": name},
            )
        )
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=resp.text,
            total_elapsed_ms=elapsed,
            prompt=prompt,
        )
