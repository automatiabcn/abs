"""ABS Central Watchdog scanner (skeleton).

Goal: on our side (Hetzner $5-10/mo VPS) runs once daily via cron,
provider pricing/changelog degisikliklerini tarar, bizi uyarir.

Not in the backend container — separate deploy. This task is only a skeleton (in 015
gercek scrape parser'lar provider basina yazilacak).
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List

logger = logging.getLogger(__name__)


# Provider docs / changelog endpoint'leri (RSS yoksa scrape hedef)
_FEEDS: Dict[str, str] = {
    "groq": "https://console.groq.com/docs/changelog",
    "anthropic": "https://docs.claude.com/en/release-notes",
    "gemini": "https://ai.google.dev/gemini-api/docs/changelog",
    "cohere": "https://docs.cohere.com/changelog",
    "cerebras": "https://inference-docs.cerebras.ai/changelog",
    "cloudflare": "https://developers.cloudflare.com/workers-ai/changelog/",
}


def list_feeds() -> Dict[str, str]:
    return dict(_FEEDS)


def scan_changelog(provider: str) -> Dict:
    """Stub — gercek scraping logic 015'te eklenecek (provider basina parser)."""
    return {
        "provider": provider,
        "scanned_at": time.time(),
        "changelog_url": _FEEDS.get(provider),
        "status": "stub",
    }


def scan_all() -> List[Dict]:
    return [scan_changelog(p) for p in _FEEDS]
