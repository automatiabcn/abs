# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Humanize_transform: LLM pass that rewrites machine-sounding text to read naturally."""

from __future__ import annotations

from app.providers.registry import get_provider


async def humanize_transform(text: str, lang: str = "tr") -> str:
    """Rephrase text so it reads as if a person wrote it."""
    instructions = (
        "Rewrite the text below so it trips AI detectors less. Preserve the "
        "meaning; drop stock phrases, heavily parallel structure and filler "
        "openers such as 'certainly' or 'in summary'. Write fluent, natural "
        "Turkish."
        if lang == "tr"
        else "Rewrite the following to sound more natural and less AI-generated. "
        "Preserve meaning; drop stock phrases and overly parallel structures."
    )
    prompt = f"{instructions}\n\nTEXT:\n{text[:6000]}"
    provider = get_provider("cloudflare")
    resp = await provider.call(prompt, model="@cf/moonshotai/kimi-k2.5")
    return resp.text or text
