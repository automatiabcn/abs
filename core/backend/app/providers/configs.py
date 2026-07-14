# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider config YAML loader.

At boot, `infra/provider-configs/*.yaml` is read into the model alias map and the
pricing dict. In a container, `ABS_PROVIDER_CONFIGS_DIR` overrides the path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def _default_dir() -> Path:
    """Repo root'taki infra/provider-configs (dev mode) veya env override."""
    override = os.environ.get("ABS_PROVIDER_CONFIGS_DIR")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    # Dev layout: core/backend/app/providers/configs.py → parents[4] = repo root.
    # In the slim container the app lives at /app/app/... so parents[4] would
    # IndexError; guard it and fall back to the conventional container mount so
    # load_all() degrades gracefully (dir-not-found → {}) instead of crashing
    # boot when ABS_PROVIDER_CONFIGS_DIR is unset.
    if len(here.parents) > 4:
        return here.parents[4] / "infra" / "provider-configs"
    return Path("/provider-configs")


_loaded: Dict[str, dict] = {}


def load_all(directory: Optional[Path] = None) -> Dict[str, dict]:
    """Read every *.yaml and return a dict of provider_name -> config."""
    d = directory or _default_dir()
    if not d.is_dir():
        logger.warning("provider config directory not found: %s", d)
        return {}
    out: Dict[str, dict] = {}
    for f in sorted(d.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "provider" in data:
                out[data["provider"]] = data
        except Exception as exc:
            logger.warning("config parse fail %s: %s", f.name, exc)
    _loaded.clear()
    _loaded.update(out)
    return out


def get(provider: str) -> Optional[dict]:
    return _loaded.get(provider)


def get_model_alias(provider: str, alias: str) -> Optional[dict]:
    cfg = _loaded.get(provider) or {}
    for m in cfg.get("models") or []:
        if m.get("alias") == alias:
            return m
    return None


def deprecated_models(provider: str) -> List[str]:
    cfg = _loaded.get(provider) or {}
    return [m["id"] for m in (cfg.get("models") or []) if m.get("deprecated")]


def all_providers() -> List[str]:
    return sorted(_loaded.keys())
