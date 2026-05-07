# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""humanize_transform: AI-izlenimli metni daha doğal hale getiren LLM çağrısı."""

from __future__ import annotations

from app.providers.registry import get_provider


async def humanize_transform(text: str, lang: str = "tr") -> str:
    """Metni daha 'insan yazmış' hissi verecek şekilde yeniden ifade et."""
    instructions = (
        "Aşağıdaki metni AI-detector'dan daha az tetiklenecek şekilde yeniden yaz. "
        "Aynı anlamı koru; stock phrase'leri, aşırı paralel yapıları ve gereksiz "
        "'kesinlikle/özetle' kalıplarını çıkar. Akıcı, doğal Türkçe kullan."
        if lang == "tr"
        else "Rewrite the following to sound more natural and less AI-generated. "
        "Preserve meaning; drop stock phrases and overly parallel structures."
    )
    prompt = f"{instructions}\n\nMETİN:\n{text[:6000]}"
    provider = get_provider("cloudflare")
    resp = await provider.call(prompt, model="@cf/moonshotai/kimi-k2.5")
    return resp.text or text
