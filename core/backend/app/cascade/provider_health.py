# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The last thing each provider said — so "ready" means answered, not configured.

The panels used to derive "ready" from three facts that are all true of a
dead provider: it has a key, its breaker is closed, it is not throttled. On
2026-08-18 the title bar said "5 providers ready" while cerebras answered
402 payment_required to every call and groq's default model had been
retired (404) — 40% of the chain. The breaker did not help: it opens after
5 failures in 60 s and closes again a minute later, so a permanently dead
key flaps between "closed" and "open" and reads as healthy most of the time.
The key was probed once, when it was set; nothing looked again.

This keeps ONE fact per (tenant, provider): the last outcome. A permanent
failure (bad key, payment required, model retired) marks the provider
degraded until the next success; transient failures (timeouts, 5xx, 429)
do not, because they say nothing about the key. Readiness readers ask
`degraded_reason(provider)`; a non-empty answer means "not ready, and here
is why", in words a person can act on.

Persisted next to the breaker so a restart does not forget what it learned.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


@dataclass
class Outcome:
    ok: bool
    permanent: bool
    detail: str
    at: float
    model: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


_LAST: Dict[str, Outcome] = {}  # key: f"{tenant}|{provider}"


def _key(tenant: Optional[str], provider: str) -> str:
    return f"{tenant or '_global'}|{provider}"


def _humanize(detail: str) -> str:
    """The provider's error, as a sentence about what to do."""
    d = detail or ""
    low = d.lower()
    if "402" in d or "payment" in low or "insufficient" in low and "credit" in low:
        return "the provider says payment is required (credit or billing) — top up or replace the key"
    if "401" in d or "unauthorized" in low or "invalid api key" in low or "api key is not configured" in low:
        return "the provider rejects the key — check or replace it"
    if "403" in d or "forbidden" in low:
        return "the provider refuses this key for this call — check its permissions"
    if "model_not_found" in low or "does not exist" in low or ("404" in d and "model" in low):
        m = re.search(r"model `?([^`'\" ]+)`?", d)
        return (
            f"the pinned model {m.group(1)} is not served any more"
            if m
            else "the pinned model is not served any more"
        )
    if "404" in d:
        return "the provider answered 404 — a wrong endpoint or a retired model"
    return "the last call failed permanently: " + d[:120]


def note_success(provider: str, *, tenant: Optional[str] = None, model: str = "") -> None:
    with _LOCK:
        _LAST[_key(tenant, provider)] = Outcome(True, False, "", time.time(), model)
    _persist()


def note_failure(
    provider: str,
    *,
    tenant: Optional[str] = None,
    permanent: bool,
    detail: str = "",
    model: str = "",
) -> None:
    with _LOCK:
        prev = _LAST.get(_key(tenant, provider))
        # A transient failure does not overwrite a standing permanent verdict
        # (a 429 after a 402 does not mean the card was topped up), and it does
        # not create one either.
        if not permanent and prev is not None and not prev.ok and prev.permanent:
            return
        _LAST[_key(tenant, provider)] = Outcome(False, permanent, detail[:300], time.time(), model)
    _persist()


def last(provider: str, tenant: Optional[str] = None) -> Optional[Outcome]:
    if not _LAST:
        _restore()
    with _LOCK:
        return _LAST.get(_key(tenant, provider)) or _LAST.get(_key(None, provider))


def degraded_reason(provider: str, tenant: Optional[str] = None) -> str:
    """Why this provider is not to be counted ready — or '' when it may be."""
    o = last(provider, tenant)
    if o is None or o.ok or not o.permanent:
        return ""
    return _humanize(o.detail)


def snapshot(tenant: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Per provider: the last outcome, humanised, for panels."""
    if not _LAST:
        _restore()
    out: Dict[str, Dict[str, Any]] = {}
    with _LOCK:
        for k, o in _LAST.items():
            t, prov = k.split("|", 1)
            if tenant is not None and t not in (tenant, "_global"):
                continue
            row = o.as_dict()
            row["reason"] = "" if (o.ok or not o.permanent) else _humanize(o.detail)
            out[prov] = row
    return out


# --- persistence ------------------------------------------------------------

def _path() -> Optional[str]:
    try:
        from app.config import settings

        d = str(getattr(settings, "data_dir", "") or "")
        return os.path.join(d, "provider_health.json") if d else None
    except Exception:  # noqa: BLE001
        return None


def _persist() -> None:
    p = _path()
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with _LOCK:
            data = {k: v.as_dict() for k, v in _LAST.items()}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception as exc:  # noqa: BLE001
        logger.debug("provider_health persist skipped: %s", exc)


def _restore() -> None:
    p = _path()
    if not p or not os.path.exists(p):
        return
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
        with _LOCK:
            for k, d in raw.items():
                _LAST[k] = Outcome(
                    bool(d.get("ok")), bool(d.get("permanent")),
                    str(d.get("detail") or ""), float(d.get("at") or 0), str(d.get("model") or ""),
                )
    except Exception as exc:  # noqa: BLE001
        logger.debug("provider_health restore skipped: %s", exc)


def reset_for_tests() -> None:
    with _LOCK:
        _LAST.clear()
