"""race_tr: Qwen32B (Groq) vs Gemini 2.5 Flash — Türkçe için."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import race_first_success
from app.providers.registry import get_provider


class RaceTrPipeline(BasePipeline):
    pipeline_type = "race-tr"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        groq = get_provider("groq")
        gemini = get_provider("gemini")

        winner = await race_first_success(
            {
                "qwen32b": groq.call(prompt, model="qwen/qwen3-32b"),
                "gemini": gemini.call(prompt, model="gemini-2.5-flash"),
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
                error="Türkçe yarışını kimse kazanmadı",
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
