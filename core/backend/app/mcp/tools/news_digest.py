"""030 Modul F — `news_digest` MCP tool.

Fans out 5 parallel `gemini_search` queries (Anthropic / OpenAI / Gemini /
GitHub trending / MCP) and assembles a markdown digest. 1h disk cache;
1-2 query failures are tolerated (the failing section gets a note).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402
from app.providers import gemini_extras as _gx  # noqa: E402
from app.providers.schemas import ProviderError  # noqa: E402

logger = logging.getLogger(__name__)

CACHE_PATH = Path("/tmp/abs_news_digest_cache.json")
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

QUERIES = [
    ("Anthropic", "Anthropic latest announcements past 7 days"),
    ("OpenAI", "OpenAI latest news and model releases past 7 days"),
    ("Gemini", "Google Gemini latest updates past 7 days"),
    ("GitHub trending", "GitHub trending repositories AI ML this week"),
    ("MCP", "Model Context Protocol news and new MCP servers past 7 days"),
]


def _read_cache() -> str | None:
    try:
        if not CACHE_PATH.exists():
            return None
        data = json.loads(CACHE_PATH.read_text())
        if time.time() - float(data.get("ts", 0)) < CACHE_TTL_SECONDS:
            return str(data.get("markdown", ""))
    except Exception:
        return None
    return None


def _write_cache(markdown: str) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps({"ts": time.time(), "markdown": markdown})
        )
    except Exception as exc:
        logger.debug("news_digest cache write failed: %s", exc)


async def _one_query(label: str, query: str) -> tuple[str, str]:
    try:
        resp = await _gx.gemini_search(query)
        return label, (resp.text or "").strip()
    except ProviderError as exc:
        return label, f"_(query failed: {exc.message})_"
    except Exception as exc:  # noqa: BLE001
        return label, f"_(query failed: {exc})_"


def _format_markdown(sections: list[tuple[str, str]]) -> str:
    lines = ["# News Digest", ""]
    for label, body in sections:
        lines.append(f"## {label}")
        lines.append("")
        lines.append(body or "_(no content)_")
        lines.append("")
    return "\n".join(lines)


@mcp_server.tool()
@with_hooks("news_digest")
async def news_digest(force_refresh: bool = False) -> str:
    """5-source AI/dev news digest (Anthropic / OpenAI / Gemini / GH / MCP).

    Cached 1h on disk. Set `force_refresh=true` to bypass the cache.
    """
    await tracker.bump("news_digest")

    if not force_refresh:
        cached = _read_cache()
        if cached:
            return cached

    sections = await asyncio.gather(*[_one_query(l, q) for l, q in QUERIES])
    markdown = _format_markdown(list(sections))
    _write_cache(markdown)
    return markdown


REGISTERED_TOOLS.extend(["news_digest"])
