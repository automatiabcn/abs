# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""race_local: Ollama phi4 vs gemma2 — yerel model yarışı (Ollama gerektirir)."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import race_first_success
from app.providers.registry import get_provider


class RaceLocalPipeline(BasePipeline):
    pipeline_type = "race-local"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        ollama = get_provider("ollama")

        winner = await race_first_success(
            {
                "phi4": ollama.call(prompt, model="phi4"),
                "gemma2": ollama.call(prompt, model="gemma2:9b"),
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
                error="Yerel Ollama yarışı kaybetti (ABS_OLLAMA_URL tanımlı mı?)",
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
