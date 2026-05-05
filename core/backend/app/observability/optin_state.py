"""BUG-V3 — Track Anthropic opt-in flips and emit a SOC2 audit row.

PROMISE.md:
  "every opt-in flip and quota-block event written to T-016 SOC2
   audit log."

Strategy: keep a tiny on-disk JSON file with the most recently
observed `anthropic_enabled` boolean. On boot, compare it to the
current setting; if they differ, emit `settings.optin.flip` to
abs.audit and rewrite the file.

The store is intentionally simple — single-process, single-write at
boot — so we don't need locks or migrations.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any

from app.observability.audit import emit_event

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = pathlib.Path("data/last_optin_state.json")


def _store_path() -> pathlib.Path:
    raw = os.getenv("ABS_OPTIN_STATE_PATH", str(DEFAULT_STORE_PATH))
    p = pathlib.Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_state(path: pathlib.Path | None = None) -> dict[str, Any]:
    p = path or _store_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict[str, Any], path: pathlib.Path | None = None) -> None:
    p = path or _store_path()
    p.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def detect_and_emit_flip(
    *,
    current_enabled: bool,
    path: pathlib.Path | None = None,
) -> bool:
    """Compare the cached state to `current_enabled` and emit when they
    differ. Returns True iff a flip was observed (and audit was emitted).

    Idempotent: a steady-state boot where no flip happened performs no
    audit emission (so quiet restarts don't pollute the chain).
    """
    p = path or _store_path()
    state = _read_state(p)
    last = state.get("anthropic_enabled")
    flipped = last is not None and bool(last) != bool(current_enabled)
    if flipped:
        emit_event(
            None,
            action="settings.optin.flip",
            outcome="success",
            reason=(
                f"anthropic_enabled={'true' if current_enabled else 'false'} "
                f"(previous={'true' if last else 'false'})"
            ),
            provider="anthropic",
        )
    # Always rewrite so the next boot has the freshest snapshot — even
    # on first-run where `last is None`.
    _write_state({"anthropic_enabled": bool(current_enabled)}, p)
    return flipped


__all__ = [
    "DEFAULT_STORE_PATH",
    "detect_and_emit_flip",
]
