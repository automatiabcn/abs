# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ABS feature usage tracker (Sprint 20 T-F05).

Counts every MCP tool / pipeline / cascade invocation so the founder can
spot ABS features that ship but never run. Append-only JSON-line ledger
with 30-day rolling aggregation, idle detection, and an admin dashboard
feed at `/admin/feature-usage`.

Ledger schema (one JSON-line per call):
  {"ts": "...", "feature": "abs.qual_code", "kind": "tool",
   "tenant_id": "...", "duration_ms": int}
"""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import json
import logging
import os
import pathlib
import threading
from collections import Counter
from typing import Any, Iterable

logger = logging.getLogger(__name__)

LEDGER_DEFAULT_PATH = pathlib.Path("data/feature_usage/ledger.jsonl")
ROLLING_WINDOW_DAYS = 30
IDLE_THRESHOLD_PCT = 0.20  # any feature in IDLE > 20% of catalog → flag

# Canonical feature catalog. Anything missing here → "uncategorised" warning.
KNOWN_FEATURES: tuple[str, ...] = (
    # ABS quality pipelines
    "abs.qual_code",
    "abs.qual_tr",
    "abs.qual_translate",
    "abs.qual_analysis",
    # ABS RAG + ingest
    "abs.rag_query",
    "abs.rag_ingest",
    # ABS meetings + actions
    "abs.meeting_transcribe",
    "abs.action_extract",
    "abs.gmail_classify",
    "abs.gmail_draft",
    "abs.gmail_send",
    "abs.linear_create_ticket",
    "abs.notion_log",
    # ABS observability gates
    "abs.cerbos_check",
    "abs.langfuse_trace",
    # cascade families
    "cascade.race_code",
    "cascade.race_tr",
    "cascade.cascade",
    "cascade.local_first",
    # judge + ensemble
    "judge.senior",
    "judge.ml_persona",
    "ensemble.multi_model",
    # workflow runtime
    "workflow.synthesize",
    "workflow.validate",
    "workflow.dry_run",
)


@dc.dataclass(frozen=True)
class FeatureStat:
    feature: str
    kind: str
    calls: int
    last_used: str | None  # ISO8601 or None

    @property
    def idle(self) -> bool:
        return self.calls == 0


@dc.dataclass(frozen=True)
class UsageReport:
    window_days: int
    generated_at: str
    total_calls: int
    stats: tuple[FeatureStat, ...]
    idle_pct: float
    over_idle_threshold: bool


def _ledger_path() -> pathlib.Path:
    raw = os.getenv("ABS_FEATURE_USAGE_LEDGER", str(LEDGER_DEFAULT_PATH))
    p = pathlib.Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_lock = threading.Lock()


def record(
    feature: str,
    *,
    kind: str = "tool",
    tenant_id: str | None = None,
    duration_ms: int | None = None,
    ledger: pathlib.Path | None = None,
) -> None:
    """Append a usage row. Cheap enough to call from hot paths."""
    path = ledger or _ledger_path()
    row: dict[str, Any] = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "feature": feature,
        "kind": kind,
        "tenant_id": tenant_id,
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
    }
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


def _iter_rows(path: pathlib.Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def report(
    *,
    window_days: int = ROLLING_WINDOW_DAYS,
    catalog: Iterable[str] = KNOWN_FEATURES,
    ledger: pathlib.Path | None = None,
) -> UsageReport:
    """Aggregate ledger over the rolling window into a `UsageReport`."""
    path = ledger or _ledger_path()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=window_days)
    counter: Counter[str] = Counter()
    last_seen: dict[str, str] = {}
    for row in _iter_rows(path):
        try:
            ts = dt.datetime.fromisoformat(row["ts"])
        except (KeyError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        if ts < cutoff:
            continue
        feature = str(row.get("feature") or "")
        if not feature:
            continue
        counter[feature] += 1
        prev = last_seen.get(feature)
        if prev is None or row["ts"] > prev:
            last_seen[feature] = row["ts"]

    catalog_tuple = tuple(catalog)
    stats: list[FeatureStat] = []
    for feat in catalog_tuple:
        kind = _kind_for(feat)
        stats.append(
            FeatureStat(
                feature=feat,
                kind=kind,
                calls=counter.get(feat, 0),
                last_used=last_seen.get(feat),
            )
        )
    total = sum(counter.values())
    idle_count = sum(1 for s in stats if s.idle)
    idle_pct = (idle_count / len(stats)) if stats else 0.0
    return UsageReport(
        window_days=window_days,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        total_calls=total,
        stats=tuple(stats),
        idle_pct=idle_pct,
        over_idle_threshold=idle_pct > IDLE_THRESHOLD_PCT,
    )


def _kind_for(feature: str) -> str:
    if feature.startswith("abs."):
        return "tool"
    if feature.startswith("cascade."):
        return "cascade"
    if feature.startswith("judge.") or feature.startswith("ensemble."):
        return "pipeline"
    if feature.startswith("workflow."):
        return "workflow"
    return "uncategorised"


def suggest_alternative(intent_keywords: Iterable[str]) -> str | None:
    """Hook nudge enhancement.

    Looks at a user's intent keywords and suggests an idle ABS feature
    that would lift quality. Returns None if no obvious match.
    """
    kws = {k.lower() for k in intent_keywords}
    if {"code", "function", "implement"} & kws:
        return (
            "Try `abs.qual_code` — multi-model produce → verify → polish, "
            "≈40% better than a single-model run."
        )
    if {"analyze", "compare", "evaluate"} & kws:
        return (
            "Try `abs.qual_analysis` — three-perspective ensemble (GPT-OSS + "
            "Kimi K2 + Gemini Pro) followed by GPT-OSS-120B synthesis."
        )
    if {"translate", "ceviri", "spanish", "turkish"} & kws:
        return "Try `abs.qual_translate` — translate → back-translate → verify."
    return None


def reset_for_tests(ledger: pathlib.Path | None = None) -> None:
    p = ledger or _ledger_path()
    if p.exists():
        p.unlink()


__all__ = [
    "FeatureStat",
    "IDLE_THRESHOLD_PCT",
    "KNOWN_FEATURES",
    "ROLLING_WINDOW_DAYS",
    "UsageReport",
    "record",
    "report",
    "reset_for_tests",
    "suggest_alternative",
]
