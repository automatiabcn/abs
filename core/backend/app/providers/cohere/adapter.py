# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cohere provider — Command R+, Aya Expanse, Embed, Rerank.

`cohere>=5.13` SDK kullanılır (AsyncClientV2).
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

from app.config import settings

from ..base import BaseProvider
from ..schemas import ProviderError, ProviderResponse


class CohereProvider(BaseProvider):
    name = "cohere"
    default_model = "command-r-plus-08-2024"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        _key = kwargs.get("api_key") or settings.cohere_api_key
        if not _key:
            raise ProviderError(
                "Cohere API key tanımlı değil", provider=self.name, transient=False
            )
        try:
            import cohere
        except ImportError as exc:
            raise ProviderError(
                "cohere paketi kurulu değil", provider=self.name, transient=False
            ) from exc

        model = model or self.default_model
        timeout = kwargs.get("timeout", 60.0)
        max_tokens = kwargs.get("max_tokens", 1024)

        client = cohere.AsyncClientV2(api_key=_key, timeout=timeout)
        start = time.monotonic()
        try:
            resp = await client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=kwargs.get("temperature", 0.3),
            )
        except Exception as exc:
            name = type(exc).__name__
            transient = name in {"TooManyRequestsError", "ServiceUnavailableError", "TimeoutError"}
            raise ProviderError(
                f"Cohere {name}: {str(exc)[:200]}",
                provider=self.name,
                transient=transient,
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        text_parts: List[str] = []
        try:
            for item in resp.message.content or []:
                t = getattr(item, "text", None)
                if t:
                    text_parts.append(t)
        except Exception as exc:
            # Don't swallow a malformed/unexpected response shape into an empty
            # success — that would record_success() + cache an empty answer and
            # poison later identical prompts. Surface it as transient so the
            # cascade fails over to the next provider.
            raise ProviderError(
                f"Cohere response parse error: {type(exc).__name__}",
                provider=self.name,
                transient=True,
            ) from exc
        text = "".join(text_parts)

        try:
            from app.cohere.alert import track_usage as _track

            _track(delta=1)
        except Exception:
            pass

        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=None,
            tokens_out=None,
        )

    async def embed(self, text: str, model: str = "embed-english-v3.0") -> List[float]:
        """Metin için tek embedding döndürür (4096-dim modern Cohere)."""
        if not settings.cohere_api_key:
            raise ProviderError(
                "Cohere API key tanımlı değil", provider=self.name, transient=False
            )
        try:
            import cohere
        except ImportError as exc:
            raise ProviderError(
                "cohere paketi kurulu değil", provider=self.name, transient=False
            ) from exc

        client = cohere.AsyncClientV2(api_key=settings.cohere_api_key, timeout=30.0)
        try:
            resp = await client.embed(
                texts=[text[:8000]],
                model=model,
                input_type="search_document",
                embedding_types=["float"],
            )
            floats = getattr(resp.embeddings, "float", None) or getattr(resp.embeddings, "float_", None)
            if not floats:
                return []
            return list(floats[0])
        except Exception as exc:
            raise ProviderError(
                f"Cohere embed: {str(exc)[:200]}", provider=self.name, transient=True
            ) from exc

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = 3,
        model: str = "rerank-multilingual-v3.0",
    ) -> List[dict]:
        """Dokümanları query'e göre sırala. [{index, text, relevance_score}] döner."""
        if not settings.cohere_api_key:
            raise ProviderError(
                "Cohere API key tanımlı değil", provider=self.name, transient=False
            )
        try:
            import cohere
        except ImportError as exc:
            raise ProviderError(
                "cohere paketi kurulu değil", provider=self.name, transient=False
            ) from exc

        client = cohere.AsyncClientV2(api_key=settings.cohere_api_key, timeout=30.0)
        try:
            resp = await client.rerank(
                model=model,
                query=query,
                documents=documents,
                top_n=min(top_n, len(documents)),
            )
            return [
                {
                    "index": r.index,
                    "text": documents[r.index],
                    "relevance_score": r.relevance_score,
                }
                for r in resp.results
            ]
        except Exception as exc:
            raise ProviderError(
                f"Cohere rerank: {str(exc)[:200]}", provider=self.name, transient=True
            ) from exc
