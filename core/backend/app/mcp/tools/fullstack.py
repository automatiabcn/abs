"""Batch F — 4 fullstack tool (fullstack, fullstack_plan, fullstack_scan, fullstack_detect)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from app.cascade.orchestrator import call_with_cascade
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.providers.schemas import ProviderError

REGISTERED_TOOLS: List[str] = []


_LAYER_MODELS: Dict[str, tuple[str, str]] = {
    "frontend": ("gemini", "gemini-2.5-pro"),
    "backend": ("groq", "openai/gpt-oss-120b"),
    "database": ("groq", "openai/gpt-oss-120b"),
    "devops": ("groq", "qwen/qwen3-32b"),
    "testing": ("cloudflare", "@cf/qwen/qwen2.5-coder-32b-instruct"),
    "docs": ("groq", "qwen/qwen3-32b"),
    "architecture": ("groq", "openai/gpt-oss-120b"),
}

_LAYER_HINTS: Dict[str, tuple[str, ...]] = {
    "frontend": (
        "react", "next.js", "nextjs", "vue", "svelte", "tailwind",
        "jsx", "tsx", "component", "landing", "ui ",
    ),
    "backend": (
        "fastapi", "flask", "django", "express", "endpoint", "api ",
        "rest", "graphql", "middleware", "router",
    ),
    "database": ("sql", "postgres", "sqlite", "mongodb", "schema", "migration", "orm"),
    "devops": (
        "docker", "kubernetes", "k8s", "ci", "cd", "github actions",
        "nginx", "caddy", "deploy",
    ),
    "testing": ("pytest", "jest", "vitest", "test case", "unit test"),
    "docs": ("readme", "dokuman", "documentation", "api doc", "kullanici kilavuz"),
    "architecture": ("mimari", "architecture", "design decision", "system design"),
}


def _detect_layer(prompt: str) -> str:
    p = prompt.lower()
    best = ("backend", 0)
    for layer, kws in _LAYER_HINTS.items():
        score = sum(1 for kw in kws if kw in p)
        if score > best[1]:
            best = (layer, score)
    return best[0]


@mcp_server.tool()
@with_hooks("fullstack_detect")
async def fullstack_detect(prompt: str) -> str:
    """Prompt'tan katman tespit et (frontend/backend/database/devops/testing/docs/architecture)."""
    await tracker.bump("fullstack_detect")
    layer = _detect_layer(prompt)
    provider, model = _LAYER_MODELS[layer]
    return json.dumps(
        {"layer": layer, "primary_provider": provider, "model": model},
        ensure_ascii=False,
    )


@mcp_server.tool()
@with_hooks("fullstack")
async def fullstack(prompt: str, layer: str = "auto") -> str:
    """Katman-özel kod üretici — auto katman tespit + en uygun model."""
    await tracker.bump("fullstack")
    if layer == "auto":
        layer = _detect_layer(prompt)
    pair = _LAYER_MODELS.get(layer)
    if not pair:
        return f"[HATA] fullstack: bilinmeyen layer '{layer}'"
    provider, model = pair
    system_hint = f"Katman: {layer}. En iyi uygulamalara uyarak üret."
    try:
        resp = await call_with_cascade(
            f"{system_hint}\n\nGörev:\n{prompt}",
            primary=provider,
            model=model,
        )
        return f"[layer={layer} · model={model}]\n\n{resp.text or ''}"
    except ProviderError as exc:
        return f"[HATA] fullstack: {exc.message}"


@mcp_server.tool()
@with_hooks("fullstack_scan")
async def fullstack_scan(project_dir: str) -> str:
    """Proje dizinini tara — dosya/lang/deps envanteri."""
    await tracker.bump("fullstack_scan")
    root = Path(project_dir)
    if not root.is_dir():
        return json.dumps(
            {"error": f"dizin yok: {project_dir}"}, ensure_ascii=False
        )
    by_ext: Dict[str, int] = {}
    total_files = 0
    total_size = 0
    manifest_files: List[str] = []
    for p in root.rglob("*"):
        # skip hidden + node_modules + .venv
        if any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in p.parts):
            continue
        if p.is_file():
            total_files += 1
            total_size += p.stat().st_size
            ext = p.suffix.lower() or "(no-ext)"
            by_ext[ext] = by_ext.get(ext, 0) + 1
            if p.name in (
                "package.json",
                "pyproject.toml",
                "Cargo.toml",
                "go.mod",
                "requirements.txt",
                "Dockerfile",
                "docker-compose.yml",
            ):
                manifest_files.append(str(p.relative_to(root)))
    return json.dumps(
        {
            "project_dir": str(root),
            "total_files": total_files,
            "total_size_kb": round(total_size / 1024, 1),
            "by_ext": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])[:10]),
            "manifests": manifest_files,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("fullstack_plan")
async def fullstack_plan(project_dir: str) -> str:
    """Scan + gap analizi + görev planı (LLM ile)."""
    await tracker.bump("fullstack_plan")
    scan = await fullstack_scan(project_dir)  # scan text
    prompt = (
        "Aşağıdaki proje envanterine bakıp eksik/iyileştirilmesi gereken "
        "maddeleri ve öncelikli 5-7 görevi Türkçe plan olarak listele:\n\n"
        + scan
    )
    try:
        resp = await call_with_cascade(
            prompt, primary="groq", model="openai/gpt-oss-120b"
        )
        return resp.text or "[HATA] fullstack_plan: empty"
    except ProviderError as exc:
        return f"[HATA] fullstack_plan: {exc.message}"


REGISTERED_TOOLS.extend(
    [
        "fullstack_detect",
        "fullstack",
        "fullstack_scan",
        "fullstack_plan",
    ]
)
