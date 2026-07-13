# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Helpers for running pipeline steps: timing, parallel fan-out, error capture."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Coroutine, Dict, Optional, Tuple

from .base import PipelineStep

logger = logging.getLogger(__name__)


async def timed_step(
    name: str,
    coro: Awaitable[Any],
    model_hint: str = "",
) -> Tuple[PipelineStep, Optional[Any]]:
    """Await a coroutine and return (PipelineStep, result).

    A failing step never propagates: it comes back as an un-ok PipelineStep
    with result None, so one dead provider cannot abort the pipeline.
    """
    start = time.monotonic()
    try:
        result = await coro
        elapsed = int((time.monotonic() - start) * 1000)
        model = model_hint or (
            getattr(result, "model", "") or getattr(result, "provider", "")
        )
        step = PipelineStep(name=name, model=model, elapsed_ms=elapsed, ok=True)
        # Forward the ProviderResponse token counts so cost can be attributed
        # Per step rather than per pipeline.
        ti = getattr(result, "tokens_in", None)
        to = getattr(result, "tokens_out", None)
        if ti is not None:
            step.meta["tokens_in"] = int(ti)
        if to is not None:
            step.meta["tokens_out"] = int(to)
        return step, result
    except Exception as exc:  # noqa: BLE001 (a step must never raise)
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info("pipeline step %s failed: %s", name, exc)
        return (
            PipelineStep(
                name=name,
                model=model_hint,
                elapsed_ms=elapsed,
                ok=False,
                error=str(exc)[:200],
            ),
            None,
        )


async def run_parallel_named(coros: Dict[str, Awaitable[Any]]) -> Dict[str, Any]:
    """Run coroutines concurrently → {name: result | Exception}. Never raises."""
    names = list(coros.keys())
    results = await asyncio.gather(*coros.values(), return_exceptions=True)
    return dict(zip(names, results))


def pick_longest_success(results: Dict[str, Any]) -> Optional[Tuple[str, Any]]:
    """Pick the result with the longest `text`, ignoring failures and empties."""
    best: Optional[Tuple[str, Any]] = None
    for name, r in results.items():
        if isinstance(r, BaseException):
            continue
        text = getattr(r, "text", "")
        if not text:
            continue
        if best is None or len(text) > len(getattr(best[1], "text", "")):
            best = (name, r)
    return best


async def race_first_success(
    coros: Dict[str, Coroutine[Any, Any, Any]],
) -> Optional[Tuple[str, Any]]:
    """Return (name, result) of the first coroutine to produce non-empty text.

    Cancels the losers, including on an early exit. None if all of them fail.
    """
    tasks = {asyncio.create_task(c): name for name, c in coros.items()}
    try:
        while tasks:
            done, _ = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                name = tasks.pop(t)
                try:
                    result = t.result()
                    # Non-empty text is the success condition; an empty
                    # Response means the provider answered nothing useful.
                    if getattr(result, "text", ""):
                        # Winner found — stop paying for the rest.
                        for other in tasks:
                            other.cancel()
                        return name, result
                except Exception as exc:  # noqa: BLE001
                    logger.info("race: %s failed: %s", name, exc)
        return None
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
