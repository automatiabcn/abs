# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""auto_verify_turkish: aya:8b ile Türkçe gramer/stil kontrol."""

from __future__ import annotations

import time

from app.config import settings
from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import timed_step
from app.providers.registry import get_provider


class AutoVerifyTurkishPipeline(BasePipeline):
    pipeline_type = "auto-verify-turkish"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        if not settings.ollama_url:
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=[
                    PipelineStep(
                        name="precheck",
                        model="-",
                        elapsed_ms=0,
                        ok=False,
                        error="Ollama not configured",
                    )
                ],
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error="ABS_OLLAMA_URL tanımlı değil — auto_verify_turkish için yerel Ollama gerekli",
            )

        ollama = get_provider("ollama")
        q = (
            "Aşağıdaki Türkçe metni gramer, yazım, akıcılık açısından kontrol et. "
            "Sorunlu cümleleri listele veya 'TAMAM' yaz:\n\n" + prompt[:6000]
        )
        step, resp = await timed_step(
            "aya-review",
            ollama.call(q, model="aya:8b"),
            model_hint="aya:8b",
        )
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=[step],
            final_response=resp.text if resp and resp.text else "",
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            error=step.error,
        )
