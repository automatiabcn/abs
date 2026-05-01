"""Panel SSE endpoint — 5 event tipi yayar (metrics/orchestrator/cohere/mcp/budget).

MVP: placeholder payload. Gerçek metrikler 005-orchestrator task'ında bağlanacak.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.auth import current_admin
from app.config import settings
from app.mcp.tracking import tracker
from app.workflow import list_workflows, stats as workflow_stats

router = APIRouter(prefix="/api", tags=["stream"])

_EVENT_ORDER = [
    "metrics",
    "orchestrator",
    "cohere-usage",
    "mcp-tools",
    "budget-today",
    "license-status",  # 011 — demo countdown + license/refund banner
    "update-available",  # 014 — release manifest banner
]

_PROVIDERS = [
    "Anthropic",
    "Groq",
    "Cerebras",
    "Gemini",
    "CloudFlare",
    "Cohere",
]


def _now_hms() -> str:
    return datetime.now(tz=timezone.utc).astimezone().strftime("%H:%M:%S")


def _build_metrics() -> dict:
    return {
        "tasks": random.randint(1400, 1600),
        "tokens": random.randint(1_800_000, 1_950_000),
        "savings_pct": random.randint(20, 35),
        "deleg_rate": round(random.uniform(12.0, 22.0), 1),
        "deleg_stats": f"{random.randint(30, 60)}/{random.randint(150, 200)}",
        "cache_hit": random.randint(30, 65),
        "gpu_temp": random.randint(45, 70),
        "gpu_vram": f"{round(random.uniform(2.5, 14.0), 1)}/16GB",
    }


def _build_orchestrator() -> dict:
    """014 — gerçek health monitor snapshot'ı (random kalktı).

    Monitor henüz veri toplamadıysa (test mode veya soğuk başlangıç) provider
    listesi 'unknown' state ile dönülür. Judge alanı 015'te gerçek judge feed'iyle dolar.
    """
    from app.health.monitor import monitor as _monitor

    snap = _monitor.snapshot()
    if not snap:
        snap = [
            {"name": p, "state": "unknown", "latency_ms": 0}
            for p in _PROVIDERS
        ]
    head = snap[0]
    return {
        "providers": snap,
        "events": [
            {
                "t": _now_hms(),
                "msg": f"{head['name']} latency {head.get('latency_ms', 0)}ms",
            }
        ],
        "judge": _build_judge_placeholder(),
    }


_JUDGE_CACHE: dict = {"data": None, "ts": 0.0}
_JUDGE_CACHE_TTL = 60  # 022 — 60s cache


def _build_judge_placeholder() -> dict:
    """022 — Judge feed: judge_log aggregate (60s cache).

    Daha önce placeholder'dı (015 deferred). Şimdi `app.judge.stats.summary()`
    çağırır ve panel SSE'ye verir. Hata olursa placeholder'a geri düşer.
    """
    import time

    now = time.time()
    if _JUDGE_CACHE["data"] is not None and (now - _JUDGE_CACHE["ts"] < _JUDGE_CACHE_TTL):
        return _JUDGE_CACHE["data"]
    try:
        from app.judge.stats import aggregate as judge_aggregate

        s = judge_aggregate()
        avg = s.get("avg_score") or s.get("avg")
        total = s.get("total_count", s.get("count", 0))
        accept_rate = s.get("accept_rate", s.get("accepted_pct", 0)) or 0
        out = {
            "score": round(avg, 1) if isinstance(avg, (int, float)) else None,
            "summary": (
                f"Son {total} patch — kabul oranı %{int(accept_rate * 100) if accept_rate <= 1 else int(accept_rate)}"
                if total
                else "Judge: henüz veri yok — judge_diff sonrası dolacak."
            ),
            "body": "",
            "real": True,
        }
    except Exception:
        out = {
            "score": None,
            "summary": "Judge: henüz veri yok — judge_diff sonrası dolacak.",
            "body": "",
            "real": False,
        }
    _JUDGE_CACHE["data"] = out
    _JUDGE_CACHE["ts"] = now
    return out


def _build_cohere() -> dict:
    count = random.randint(120, 960)
    limit = 1000
    return {
        "count": count,
        "limit": limit,
        "warning": count > 800,
        "detail": (
            "Cohere günlük quota %80'i geçti."
            if count > 800
            else "Kullanım normal aralıkta."
        ),
    }


def _build_mcp_tools() -> dict:
    """010 — gerçek tracker.snapshot() top-N tool count (random tablo kalktı)."""
    snap = tracker.snapshot()
    counts: list[tuple[str, int]] = sorted(
        ((k, int(v["count_24h"])) for k, v in snap.items()),
        key=lambda kv: -kv[1],
    )[:8]
    tools = [{"name": k, "count_24h": c} for k, c in counts]
    return {
        "tools": tools,
        "total_24h": sum(c for _, c in counts),
    }


def _build_budget() -> dict:
    """015 — gerçek today_usd (cost_estimator) + learnings_count (recent_count). workflow gerçek."""
    from app.billing.cost_estimator import estimate_daily_cost
    from app.learnings.store import recent_count

    cost = estimate_daily_cost()
    wf = workflow_stats()
    recent = list_workflows(limit=5)
    by_status = wf.get("by_status", {})
    ok_count = by_status.get("ok", 0)
    total = wf.get("total_workflows", 0)
    return {
        "today_usd": cost["today_usd"],
        "projected_monthly_usd": cost["projected_monthly_usd"],
        "learnings_count": recent_count(window_days=30),
        "workflow": {
            "summary": f"{ok_count}/{total} ok",
            "items": [
                {
                    "id": w["id"][:8],
                    "status": w["status"],
                    "step": w["type"],
                }
                for w in recent
            ],
        },
    }


def _build_license_status() -> dict:
    """011 — Panel banner feed: demo countdown + license/refund durumu."""
    from app.licensing.demo import status as demo_status
    from app.mcp.gate import _gate_status

    g = _gate_status()
    d = demo_status()
    return {
        "license_active": g["license_active"],
        "demo_active": g["demo_active"],
        "demo_started": d.get("started", False),
        "demo_days_remaining": d.get("days_remaining"),
        "demo_expires_at": d.get("expires_at"),
        "require_license": settings.mcp_require_license,
        "allowed": g["allowed"],
        "purchase_url": "https://abs.automatiabcn.com/",
    }


async def _build_update_available() -> dict:
    """014 — Async builder: remote manifest fetch + version compare."""
    from app.main import app as fastapi_app
    from app.update.manifest import fetch_manifest, update_state

    manifest = await fetch_manifest()
    return update_state(manifest, fastapi_app.version)


_BUILDERS = {
    "metrics": _build_metrics,
    "orchestrator": _build_orchestrator,
    "cohere-usage": _build_cohere,
    "mcp-tools": _build_mcp_tools,
    "budget-today": _build_budget,
    "license-status": _build_license_status,
    "update-available": _build_update_available,
}


async def _event_generator(request: Request) -> AsyncIterator[str]:
    """SSE akışı — client kapanana kadar 2sn aralıkla rotating event yayar.

    014 — _BUILDERS hem sync hem async fn destekler (`update-available`
    `fetch_manifest` çağrısı için async).
    """
    import inspect

    i = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            ev_name = _EVENT_ORDER[i % len(_EVENT_ORDER)]
            builder = _BUILDERS[ev_name]
            try:
                if inspect.iscoroutinefunction(builder):
                    payload = await builder()
                else:
                    payload = builder()
            except Exception:
                payload = {"error": "builder fail"}
            yield f"event: {ev_name}\ndata: {json.dumps(payload)}\n\n"
            i += 1
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        return


@router.get("/stream")
async def stream(
    request: Request,
    _admin: dict = Depends(current_admin),
) -> StreamingResponse:
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
