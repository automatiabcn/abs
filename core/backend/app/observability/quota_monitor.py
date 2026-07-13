# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Claude API quota monitor.

Tracks per-month token usage when ABS hits Anthropic. Two thresholds:
  - WARN_PCT  (default 80%) — emit a warning + LangFuse trace; UI banner.
  - BLOCK_PCT (default 95%) — refuse new Claude calls; caller should fall back
    to GPT-OSS / Cascade.

Free path (`groq`, `cloudflare`, `gemini`, `cohere`, `ollama`) is exempt and
never hits this module. Storage is an append-only JSON-line ledger so audit
chains stay single-source-of-truth (T-016 compatible).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


WARN_PCT_DEFAULT = 0.80
BLOCK_PCT_DEFAULT = 0.95
DEFAULT_MONTHLY_LIMIT_TOKENS = 1_000_000  # Claude Plus equivalent baseline
LEDGER_DEFAULT_PATH = pathlib.Path("data/quota/claude_tokens.jsonl")


class QuotaExceeded(RuntimeError):
    """Raised when a Claude call would breach the BLOCK threshold."""


@dataclass(frozen=True)
class QuotaStatus:
    month: str  # YYYY-MM
    limit_tokens: int
    used_tokens: int
    used_pct: float
    over_warn: bool
    over_block: bool

    def banner(self) -> str | None:
        if self.over_block:
            return f"Claude budget {self.used_pct * 100:.0f}% used — blocked, falling back to GPT-OSS."
        if self.over_warn:
            return f"Claude budget {self.used_pct * 100:.0f}% used — consider using free providers."
        return None


def _ledger_path() -> pathlib.Path:
    raw = os.getenv("ABS_CLAUDE_QUOTA_LEDGER", str(LEDGER_DEFAULT_PATH))
    p = pathlib.Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _monthly_limit() -> int:
    return int(
        os.getenv("ABS_CLAUDE_MONTHLY_TOKEN_LIMIT", DEFAULT_MONTHLY_LIMIT_TOKENS)
    )


def _warn_pct() -> float:
    return float(os.getenv("ABS_CLAUDE_QUOTA_WARN_PCT", WARN_PCT_DEFAULT))


def _block_pct() -> float:
    return float(os.getenv("ABS_CLAUDE_QUOTA_BLOCK_PCT", BLOCK_PCT_DEFAULT))


_lock = threading.Lock()


def _current_month() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def _read_used(*, ledger: pathlib.Path | None = None, month: str | None = None) -> int:
    path = ledger or _ledger_path()
    target_month = month or _current_month()
    if not path.exists():
        return 0
    used = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("month") == target_month:
                try:
                    tok = int(row.get("tokens", 0))
                except (TypeError, ValueError):
                    continue
                # a corrupted/negative ledger row must not shrink the
                # running total (which would silently widen the quota).
                if tok > 0:
                    used += tok
    return used


def status(*, ledger: pathlib.Path | None = None) -> QuotaStatus:
    used = _read_used(ledger=ledger)
    limit = _monthly_limit()
    pct = used / limit if limit > 0 else 0.0
    return QuotaStatus(
        month=_current_month(),
        limit_tokens=limit,
        used_tokens=used,
        used_pct=pct,
        over_warn=pct >= _warn_pct(),
        over_block=pct >= _block_pct(),
    )


def gate(
    *, requested_tokens: int = 0, ledger: pathlib.Path | None = None
) -> QuotaStatus:
    """Pre-flight check — call before issuing the Claude request.

    Raises QuotaExceeded when (used + requested) >= BLOCK_PCT * limit. The
    caller then falls back to a free provider via the cascade.

    BUG-V3 — emits a `quota.block` audit row on every refusal so the
    SOC2 chain has the same observability the PROMISE.md vow advertises.
    """
    s = status(ledger=ledger)
    projected = s.used_tokens + max(0, requested_tokens)
    if projected >= _block_pct() * s.limit_tokens:
        logger.warning(
            "claude_quota_block month=%s used=%d projected=%d limit=%d",
            s.month,
            s.used_tokens,
            projected,
            s.limit_tokens,
        )
        # BUG-V3 — emit audit. Imported lazily so this module stays
        # decoupled from the FastAPI / starlette stack at import time.
        try:
            from app.observability.audit import emit_event

            emit_event(
                None,
                action="quota.block",
                outcome="denied",
                reason=(
                    f"claude budget {s.used_pct * 100:.0f}% reached "
                    f"(projected {projected}/{s.limit_tokens})"
                ),
                provider="anthropic",
            )
        except Exception:  # noqa: BLE001 — audit failures never block the gate
            logger.debug("quota.block audit emit skipped", exc_info=True)
        raise QuotaExceeded(
            f"Claude monthly token quota would breach block threshold "
            f"({projected}/{s.limit_tokens}); falling back to free provider"
        )
    return s


def record(
    *,
    tokens_in: int,
    tokens_out: int,
    model: str,
    tenant_id: str | None = None,
    ledger: pathlib.Path | None = None,
) -> QuotaStatus:
    """Append a usage row after a Claude call returns."""
    path = ledger or _ledger_path()
    row: dict[str, Any] = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "month": _current_month(),
        "model": model,
        "tenant_id": tenant_id,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "tokens": int(tokens_in or 0) + int(tokens_out or 0),
    }
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    s = status(ledger=path)
    if s.over_block:
        logger.warning(
            "claude_quota_over_block month=%s pct=%.1f%%", s.month, s.used_pct * 100
        )
    elif s.over_warn:
        logger.info(
            "claude_quota_over_warn month=%s pct=%.1f%%", s.month, s.used_pct * 100
        )
    # BUG-V5 — push the rolling monthly used-pct as a LangFuse score
    # so the dashboard time-series matches the PROMISE.md vow
    # ("LangFuse dashboard `claude_tokens_used_pct_month` time-series").
    _push_langfuse_pct(s)
    return s


def _push_langfuse_pct(s: QuotaStatus) -> None:
    """Best-effort emit a `claude_tokens_used_pct_month` score to LangFuse.

    Failures (LangFuse disabled, network blip, missing SDK) are
    swallowed — the quota gate must never fail just because metrics
    are down.
    """
    try:
        from app.observability.langfuse_client import get_langfuse, is_enabled

        if not is_enabled():
            return
        client = get_langfuse()
        if client is None:
            return
        score = getattr(client, "score", None)
        if score is None:
            return
        score(
            name="claude_tokens_used_pct_month",
            value=float(s.used_pct),
            comment=f"month={s.month} used={s.used_tokens}/{s.limit_tokens}",
        )
    except Exception:  # noqa: BLE001 — observability never blocks
        logger.debug(
            "langfuse claude_tokens_used_pct_month emit skipped", exc_info=True
        )


def reset_for_tests(ledger: pathlib.Path | None = None) -> None:
    path = ledger or _ledger_path()
    if path.exists():
        path.unlink()


__all__ = [
    "BLOCK_PCT_DEFAULT",
    "DEFAULT_MONTHLY_LIMIT_TOKENS",
    "QuotaExceeded",
    "QuotaStatus",
    "WARN_PCT_DEFAULT",
    "gate",
    "record",
    "reset_for_tests",
    "status",
]
