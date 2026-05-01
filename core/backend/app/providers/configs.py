"""014 — Provider config YAML loader.

Boot'ta `infra/provider-configs/*.yaml` okunur, model alias map + pricing dict'e
yuklenir. Docker container'da `ABS_PROVIDER_CONFIGS_DIR` env ile path override edilebilir.
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
    # core/backend/app/providers/configs.py → parents[4] = abs-server-product
    return Path(__file__).resolve().parents[4] / "infra" / "provider-configs"


_loaded: Dict[str, dict] = {}


def load_all(directory: Optional[Path] = None) -> Dict[str, dict]:
    """Tum *.yaml dosyalarini oku, dict (provider_name → config) dondur."""
    d = directory or _default_dir()
    if not d.is_dir():
        logger.warning("provider configs dir bulunamadi: %s", d)
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
