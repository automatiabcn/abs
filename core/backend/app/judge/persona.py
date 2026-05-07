# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Persona (fingerprint) yükleyici.

MVP: `default_python` personası (professional baseline). 009-rag task'ında
müşteri kendi fingerprint JSON'ını `settings.cache_dir/persona.json`'a koyup
override edebilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from app.config import settings


DEFAULT_PERSONA: Dict[str, float] = {
    # Hedef oranlar — professional Python kodlama baseline
    "docstring_ratio": 0.60,
    "type_hints_ratio": 0.70,
    "avg_func_lines": 20.0,
}


def load_persona() -> Dict[str, float]:
    path = Path(settings.cache_dir) / "persona.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_PERSONA)
