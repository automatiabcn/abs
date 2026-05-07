# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""auto_verify_code: 3 yerel model paralel (granite-2b security + codellama test + deepseek lint).

Ollama gerektirir. ABS_OLLAMA_URL yoksa error.
"""

from __future__ import annotations

import time

from app.config import settings
from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import run_parallel_named
from app.providers.registry import get_provider


class AutoVerifyCodePipeline(BasePipeline):
    pipeline_type = "auto-verify-code"

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
                error="ABS_OLLAMA_URL tanımlı değil — auto_verify_code için yerel Ollama gerekli",
            )

        code = prompt.strip()[:8000]
        ollama = get_provider("ollama")

        sec_q = "Güvenlik açıkları (SQLi, RCE, hardcoded secret) varsa listele, yoksa 'CLEAN' yaz:\n\n" + code
        test_q = "Bu kod için 1-2 pytest test fonksiyonu yaz:\n\n" + code
        lint_q = "Bu kodda linting sorunları var mı? Varsa kısa listele, yoksa 'CLEAN' yaz:\n\n" + code

        parallel_start = time.monotonic()
        results = await run_parallel_named(
            {
                "security": ollama.call(sec_q, model="granite3.1-dense:2b"),
                "test": ollama.call(test_q, model="codellama:7b"),
                "lint": ollama.call(lint_q, model="deepseek-coder:6.7b"),
            }
        )
        parallel_ms = int((time.monotonic() - parallel_start) * 1000)

        ok_names = [
            n
            for n, r in results.items()
            if not isinstance(r, BaseException) and getattr(r, "text", "")
        ]

        steps: list[PipelineStep] = [
            PipelineStep(
                name="3-verifiers",
                model="+".join(ok_names) or "-",
                elapsed_ms=parallel_ms,
                ok=bool(ok_names),
                meta={"succeeded": ok_names},
            )
        ]

        report_parts: list[str] = []
        for n in ("security", "test", "lint"):
            r = results.get(n)
            if isinstance(r, BaseException):
                report_parts.append(f"=== {n.upper()} ===\n[HATA] {r}")
            elif r is None:
                report_parts.append(f"=== {n.upper()} ===\n[BOŞ]")
            else:
                report_parts.append(f"=== {n.upper()} ===\n{r.text[:2000]}")

        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response="\n\n".join(report_parts),
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
        )
