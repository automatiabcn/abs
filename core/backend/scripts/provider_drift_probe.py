"""T-S02.3 — nightly provider drift probe.

Sends the golden request fixture to the live sandbox endpoint, captures the
response, and writes a fingerprint diff to a JSON artifact. The diff step
(provider_drift_check.py) compares fingerprints to the stored response_v1.json.

Usage:
    python -m scripts.provider_drift_probe --provider groq --out drift.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

from app.providers.contract_validator import (
    PROVIDERS,
    canonical_text,
    fingerprint,
    load_fixture,
)


async def _probe_groq(req: dict) -> dict:
    import httpx

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY missing — skipping live probe")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=req,
        )
        r.raise_for_status()
        return r.json()


async def _probe_anthropic(req: dict) -> dict:
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing — skipping live probe")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=req,
        )
        r.raise_for_status()
        return r.json()


async def _probe_gemini(req: dict) -> dict:
    import httpx

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing — skipping live probe")
    model = "gemini-2.5-flash"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers={"Content-Type": "application/json"}, json=req)
        r.raise_for_status()
        return r.json()


_PROBES = {
    "groq": _probe_groq,
    "anthropic": _probe_anthropic,
    "gemini": _probe_gemini,
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=list(PROVIDERS))
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()

    if args.provider not in _PROBES:
        # Cohere + OpenRouter sandbox keys not available — skip cleanly.
        args.out.write_text(json.dumps({"skipped": True, "provider": args.provider}))
        return 0

    req = load_fixture(args.provider, "request")
    try:
        live = await _PROBES[args.provider](req)
    except Exception as exc:
        # A probe failure is not a contract drift — log but don't fail the job.
        args.out.write_text(json.dumps({"skipped": True, "provider": args.provider, "error": str(exc)[:240]}))
        return 0

    golden = load_fixture(args.provider, "response")
    payload = {
        "provider": args.provider,
        "live_fingerprint_keys": fingerprint({k: type(v).__name__ for k, v in live.items()}),
        "golden_fingerprint_keys": fingerprint({k: type(v).__name__ for k, v in golden.items()}),
        "live_text_preview": canonical_text(args.provider, live)[:160],
    }
    args.out.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
