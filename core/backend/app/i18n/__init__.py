# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""i18n module: t(key, lang) + Accept-Language detection.

Locale JSON flat key dot notation (errors.stripe_not_configured).
EN is the default; a key missing from TR/ES falls back to EN.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SUPPORTED_LANGS = ("en", "tr", "es")
DEFAULT_LANG = "en"

_LOCALE_DIR = Path(__file__).parent / "locales"
_locales: Dict[str, Dict[str, str]] = {}


def _load_locales() -> None:
    if _locales:
        return
    for lang in SUPPORTED_LANGS:
        path = _LOCALE_DIR / f"{lang}.json"
        try:
            _locales[lang] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("locale %s load failed: %s", lang, exc)
            _locales[lang] = {}


def t(key: str, lang: Optional[str] = None, **fmt) -> str:
    """Translate key. Falls back to EN; then to key itself if missing."""
    _load_locales()
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    msg = _locales.get(lang, {}).get(key)
    if msg is None:
        msg = _locales.get(DEFAULT_LANG, {}).get(key)
    if msg is None:
        return key
    if fmt:
        try:
            return msg.format(**fmt)
        except Exception:
            return msg
    return msg


def detect_lang(accept_language: Optional[str]) -> str:
    """Parse Accept-Language header → return supported lang or default.

    Examples:
      'tr-TR,tr;q=0.9,en;q=0.8' → 'tr'
      'es-ES' → 'es'
      None / '' → 'en'
    """
    if not accept_language:
        return DEFAULT_LANG
    # parse comma-separated, take first 2 chars of each tag
    for chunk in accept_language.split(","):
        tag = chunk.split(";")[0].strip().lower()
        if not tag:
            continue
        prefix = tag[:2]
        if prefix in SUPPORTED_LANGS:
            return prefix
    return DEFAULT_LANG


def set_lang_cookie(response, lang: str) -> None:
    """Persist NEXT_LOCALE cookie for cross-request stickiness."""
    if lang in SUPPORTED_LANGS:
        response.set_cookie(
            "NEXT_LOCALE", lang, max_age=60 * 60 * 24 * 365, samesite="lax"
        )
