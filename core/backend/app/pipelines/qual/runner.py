# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2C ITEM-3 - qual_* pipeline runner."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QualStage:
    name: str
    provider: str
    elapsed_ms: int
    ok: bool
    error: Optional[str] = None


@dataclass
class QualResult:
    pipeline_id: str
    completion: str
    providers: List[str] = field(default_factory=list)
    verified: bool = False
    revisions: int = 0
    stages: List[QualStage] = field(default_factory=list)
    elapsed_ms: int = 0
    fallback: bool = False
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "completion": self.completion,
            "providers": self.providers,
            "verified": self.verified,
            "revisions": self.revisions,
            "stages": [
                {
                    "name": s.name,
                    "provider": s.provider,
                    "elapsed_ms": s.elapsed_ms,
                    "ok": s.ok,
                    "error": s.error,
                }
                for s in self.stages
            ],
            "elapsed_ms": self.elapsed_ms,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
        }


CallProvider = Callable[[str, str], Awaitable[str]]


async def _default_call_provider(provider_runtime: str, prompt: str) -> str:
    from app.cascade.orchestrator import call_with_cascade

    resp = await call_with_cascade(
        prompt,
        primary=provider_runtime,
        fallbacks=(),
        use_cache=False,
        max_tokens=1024,
    )
    text = (getattr(resp, "text", "") or "").strip()
    if not text:
        raise RuntimeError(f"empty_completion_from_{provider_runtime}")
    return text


async def _fallback_single_provider(prompt: str) -> str:
    from app.api.chat import _run_cascade

    resp = await _run_cascade(prompt, max_tokens=1024)
    return getattr(resp, "completion", "") or ""


async def run_stage(
    pipeline_id: str,
    name: str,
    provider: str,
    prompt: str,
    *,
    call_provider: CallProvider,
) -> tuple[QualStage, str]:
    started = time.perf_counter()
    try:
        text = await call_provider(provider, prompt)
        elapsed = int((time.perf_counter() - started) * 1000)
        return (
            QualStage(name=name, provider=provider, elapsed_ms=elapsed, ok=True),
            text,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.info(
            "qual stage %s/%s/%s failed: %s",
            pipeline_id,
            name,
            provider,
            exc,
        )
        return (
            QualStage(
                name=name,
                provider=provider,
                elapsed_ms=elapsed,
                ok=False,
                error=str(exc)[:200],
            ),
            "",
        )


async def run_qual_pipeline(
    pipeline_id: str,
    prompt: str,
    *,
    call_provider: Optional[CallProvider] = None,
) -> QualResult:
    handler = QUAL_HANDLERS.get(pipeline_id)
    if handler is None:
        completion = await _fallback_single_provider(prompt)
        return QualResult(
            pipeline_id=pipeline_id,
            completion=completion,
            fallback=True,
            fallback_reason=f"unknown_pipeline:{pipeline_id}",
        )

    cp = call_provider or _default_call_provider
    started = time.perf_counter()
    try:
        result = await handler(prompt, cp)
    except Exception as exc:
        logger.warning("qual pipeline %s crashed: %s", pipeline_id, exc)
        completion = await _fallback_single_provider(prompt)
        result = QualResult(
            pipeline_id=pipeline_id,
            completion=completion,
            fallback=True,
            fallback_reason=str(exc)[:200],
        )
    if not result.elapsed_ms:
        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result


QUAL_HANDLERS: Dict[str, Callable[[str, CallProvider], Awaitable[QualResult]]] = {}


def _register(
    pipeline_id: str,
    handler: Callable[[str, CallProvider], Awaitable[QualResult]],
) -> None:
    QUAL_HANDLERS[pipeline_id] = handler


from . import code, turkish, analysis, translate  # noqa: E402,F401
