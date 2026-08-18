# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pinned models against the live catalogue — the retirement watch.

Why this exists (2026-08-18): Groq retired its Llama 3.x / Qwen3-32B / Kimi
line on 08-16. The product pinned those names in fifteen files. For two days
every panel said "groq · ready" (a key was set, the breaker was closed) while
Tab returned nothing, `ask_groq_fast` answered 404, and the free chain paid a
404 on every call before failing over. Nothing measured "does the model we
pinned still exist" — a key probe at set-time is not that.

This module knows every model the code pins (one registry, so a new pin has to
be declared here to be watched) and asks each provider's model listing whether
those names still exist. It runs at start and daily, keeps the last verdict,
and the verdict is read by `model_health`, `title_status` and the panels — a
retired pin is announced with its name, not discovered by a silent feature.

Honesty rules, same as elsewhere: a provider we could not reach is `unknown`,
not "all fine" and not "all retired"; a provider with no listing endpoint we
know how to read is `unchecked` and says so.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)

# How often the watch re-asks. Providers retire on a schedule of weeks; a day
# is fine, and one listing call a day costs no quota that matters.
INTERVAL_S = 24 * 3600
_TIMEOUT_S = 8.0


def pinned_models() -> Dict[str, Set[str]]:
    """Every (provider → model ids) the code pins, gathered from the pinning
    sites themselves so the registry cannot drift from the code it watches."""
    pins: Dict[str, Set[str]] = {}

    def add(provider: str, *models: Optional[str]) -> None:
        for m in models:
            if m:
                pins.setdefault(provider, set()).add(m)

    try:
        from app.providers.groq.adapter import DEFAULT_MODEL as _groq_default
        from app.providers.groq.v1 import SUPPORTED_MODELS as _groq_supported

        add("groq", _groq_default, *_groq_supported)
    except Exception as exc:  # noqa: BLE001 — a missing import is a bug, but not here
        logger.debug("catalog_watch: groq pins unavailable: %s", exc)
    try:
        from app.providers.cerebras import CerebrasProvider

        add("cerebras", getattr(CerebrasProvider, "default_model", None))
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: cerebras pins unavailable: %s", exc)
    try:
        from app.fim.complete import _FAST_MODELS

        for prov, model in _FAST_MODELS.items():
            add(prov, model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: fim pins unavailable: %s", exc)
    try:
        from app.judge.senior import _JUDGE_ROUTES

        for prov, model in _JUDGE_ROUTES:
            add(prov, model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: judge pins unavailable: %s", exc)
    try:
        from app.disagreement.detector import PREFERRED

        for prov, model in PREFERRED:
            add(prov, model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: disagree pins unavailable: %s", exc)
    try:
        from app.mcp.tools.fullstack import _LAYER_MODELS

        for prov, model in _LAYER_MODELS.values():
            add(prov, model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: fullstack pins unavailable: %s", exc)
    try:
        from app.cascade.ollama_first import DEFAULT_MODELS as _of_models

        for prov, model in _of_models.items():
            add(prov, model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch: ollama_first pins unavailable: %s", exc)
    return pins


# Providers whose model listing we know how to read. Others are reported as
# `unchecked` — better than pretending.
_LISTINGS = {
    "groq": ("https://api.groq.com/openai/v1/models", "groq_api_key"),
    "cerebras": ("https://api.cerebras.ai/v1/models", "cerebras_api_key"),
}


@dataclass
class ProviderVerdict:
    provider: str
    status: str  # ok | retired | unknown | unchecked | no_key
    pinned: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    live_count: Optional[int] = None
    detail: str = ""
    checked_at: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "pinned": sorted(self.pinned),
            "missing": sorted(self.missing),
            "live_count": self.live_count,
            "detail": self.detail,
            "checked_at": self.checked_at,
        }


async def _live_ids(url: str, api_key: str) -> Set[str]:
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    data = r.json()
    rows = data.get("data") if isinstance(data, dict) else data
    ids: Set[str] = set()
    for row in rows or []:
        mid = row.get("id") if isinstance(row, dict) else None
        if mid:
            ids.add(str(mid))
    return ids


async def check_provider(
    provider: str, pins: Iterable[str], api_key: Optional[str] = None
) -> ProviderVerdict:
    pinned = sorted(set(pins))
    now = time.time()
    if provider not in _LISTINGS:
        return ProviderVerdict(
            provider, "unchecked", pinned, [], None,
            "no model listing this watch knows how to read", now,
        )
    url, attr = _LISTINGS[provider]
    key = api_key
    if key is None:
        try:
            from app.config import settings

            key = str(getattr(settings, attr, "") or "")
        except Exception:  # noqa: BLE001
            key = ""
    if not key:
        return ProviderVerdict(provider, "no_key", pinned, [], None, "no key to ask with", now)
    try:
        live = await _live_ids(url, key)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        return ProviderVerdict(
            provider, "unknown", pinned, [], None,
            f"listing answered {code} — cannot tell what is retired", now,
        )
    except Exception as exc:  # noqa: BLE001 — network is not a verdict
        return ProviderVerdict(
            provider, "unknown", pinned, [], None, f"listing unreachable: {exc}", now
        )
    missing = [m for m in pinned if m not in live]
    return ProviderVerdict(
        provider,
        "retired" if missing else "ok",
        pinned,
        missing,
        len(live),
        (f"{len(missing)} pinned model(s) no longer in the catalogue" if missing else ""),
        now,
    )


# Last verdicts, per provider — read by model_health / title_status. In memory
# plus a small file so a restart does not forget what it learned yesterday.
_LAST: Dict[str, ProviderVerdict] = {}


def _state_path() -> Optional[str]:
    try:
        from app.config import settings

        d = str(getattr(settings, "data_dir", "") or "")
        return os.path.join(d, "catalog_watch.json") if d else None
    except Exception:  # noqa: BLE001
        return None


def _persist() -> None:
    p = _state_path()
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({k: v.as_dict() for k, v in _LAST.items()}, fh)
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch persist skipped: %s", exc)


def _restore() -> None:
    p = _state_path()
    if not p or not os.path.exists(p):
        return
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
        for prov, d in raw.items():
            _LAST[prov] = ProviderVerdict(
                provider=prov,
                status=d.get("status", "unknown"),
                pinned=list(d.get("pinned") or []),
                missing=list(d.get("missing") or []),
                live_count=d.get("live_count"),
                detail=d.get("detail", ""),
                checked_at=d.get("checked_at"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("catalog_watch restore skipped: %s", exc)


async def run_once() -> Dict[str, ProviderVerdict]:
    """Check every pinned provider once; remember and return the verdicts."""
    pins = pinned_models()
    verdicts = await asyncio.gather(
        *(check_provider(prov, models) for prov, models in sorted(pins.items()))
    )
    for v in verdicts:
        _LAST[v.provider] = v
        if v.status == "retired":
            logger.warning(
                "catalog_watch: %s retired pinned model(s): %s",
                v.provider,
                ", ".join(v.missing),
            )
        elif v.status == "unknown":
            logger.info("catalog_watch: %s could not be checked: %s", v.provider, v.detail)
    _persist()
    return dict(_LAST)


def last_verdicts() -> Dict[str, Dict[str, Any]]:
    if not _LAST:
        _restore()
    return {k: v.as_dict() for k, v in _LAST.items()}


def retired_models(provider: str) -> List[str]:
    """Pinned models of `provider` known to be gone — [] when unknown/unchecked."""
    if not _LAST:
        _restore()
    v = _LAST.get(provider)
    return list(v.missing) if v and v.status == "retired" else []


async def watch_loop(interval_s: float = INTERVAL_S) -> None:
    """Start-up check, then one a day. Never raises out of the loop."""
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the watch must outlive a bad day
            logger.warning("catalog_watch run failed: %s", exc)
        await asyncio.sleep(interval_s)
